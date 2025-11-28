import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import ta
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from bs4 import BeautifulSoup
import yfinance as yf

st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")

# ---------------------------------------------------------
# 0. 인기 종목 매핑
# ---------------------------------------------------------
TOP_STOCKS = {
    "삼성전자": "005930", "삼전": "005930", 
    "SK하이닉스": "000660", "하이닉스": "000660",
    "현대차": "005380", "현대자동차": "005380",
    "기아": "000270", "기아차": "000270",
    "LG에너지솔루션": "373220", "엔솔": "373220",
    "POSCO홀딩스": "005490", "포스코": "005490",
    "NAVER": "035420", "네이버": "035420",
    "카카오": "035720", "셀트리온": "068270",
    "삼성SDI": "006400", "LG화학": "051910",
    "에코프로": "086520", "에코프로비엠": "247540",
    "KB금융": "105560", "신한지주": "055550",
    "테슬라": "TSLA", "애플": "AAPL", "엔비디아": "NVDA", "마이크로소프트": "MSFT",
    "구글": "GOOGL", "아마존": "AMZN", "QQQ": "QQQ", "SPY": "SPY", "SOXL": "SOXL",
    "TIGER 2차전지": "305540", "KODEX 200": "069500"
}

# ---------------------------------------------------------
# 1. 재무 데이터 (네이버/야후)
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': ''}
    
    # [한국 주식]
    if code.isdigit():
        data['Type'] = 'KR'
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 기본 지표
            try: data['PER'] = float(soup.select_one('#_per').text.replace(',', ''))
            except: pass
            try: data['PBR'] = float(soup.select_one('#_pbr').text.replace(',', ''))
            except: pass
            try:
                cap_text = soup.select_one('#_market_sum').text
                parts = cap_text.split('조')
                trillion = int(parts[0].replace(',', '').strip()) * 1000000000000
                billion = int(parts[1].replace(',', '').strip()) * 100000000 if len(parts) > 1 else 0
                data['Marcap'] = trillion + billion
            except: pass

            # 영업이익 & ROE
            try:
                dfs = pd.read_html(response.text, match='매출액')
                if dfs:
                    fin_df = dfs[-1]
                    target_col = -2
                    op_row = fin_df[fin_df.iloc[:, 0].str.contains('영업이익', na=False)]
                    if not op_row.empty: 
                        val = op_row.iloc[0, target_col]
                        data['OperatingProfit'] = f"{val} 억원"
                    roe_row = fin_df[fin_df.iloc[:, 0].str.contains('ROE', na=False)]
                    if not roe_row.empty: 
                        val = roe_row.iloc[0, target_col]
                        data['ROE'] = f"{val} %"
            except: pass
        except: pass

    # [미국 주식]
    else:
        data['Type'] = 'US'
        try:
            stock = yf.Ticker(code)
            info = stock.info
            if info.get('quoteType') == 'ETF': data['Type'] = 'ETF'
            data['PER'] = info.get('trailingPE', 0)
            data['PBR'] = info.get('priceToBook', 0)
            data['Marcap'] = info.get('marketCap', 0)
            if info.get('returnOnEquity'): data['ROE'] = f"{info.get('returnOnEquity')*100:.2f} %"
            if info.get('totalRevenue') and info.get('operatingMargins'):
                op_val = info.get('totalRevenue') * info.get('operatingMargins')
                data['OperatingProfit'] = f"{op_val / 1000000000:.2f} B ($)"
        except: pass
    return data

# ---------------------------------------------------------
# 2. 차트 데이터 (안전장치 강화)
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2)
        
        # 1차: FinanceDataReader
        try:
            if code.isdigit():
                df = fdr.DataReader(code, start, end)
                if df.empty: df = fdr.DataReader(f"{code}.KS", start, end)
                if df.empty: df = fdr.DataReader(f"{code}.KQ", start, end)
            else:
                df = fdr.DataReader(code, start, end)
        except:
            df = pd.DataFrame()

        # 2차: Yahoo Finance
        if df.empty or len(df) < 10:
            try:
                yf_ticker = f"{code}.KS" if code.isdigit() else code
                df = yf.download(yf_ticker, start=start, end=end, progress=False)
                
                # [중요] 야후 데이터 컬럼 평탄화
                if isinstance(df.columns, pd.MultiIndex):
                    try: df.columns = df.columns.get_level_values(0)
                    except: pass
            except: pass

        # 데이터 정리
        df = df.dropna(subset=['Close'])
        
        if df.empty or len(df) < 60: 
            return None, "데이터 로딩 실패"
            
        return df, None
    except Exception as e: return None, str(e)

# ---------------------------------------------------------
# 3. 상세 분석 로직 (1차 에러 방지)
# ---------------------------------------------------------
def analyze_advanced(df, fund_data):
    # [1차 안전장치] 컬럼 미리 생성
    for col in ['ma5', 'ma20', 'ma60', 'rsi', 'macd', 'macd_signal', 'macd_diff', 'bb_h', 'bb_l']:
        df[col] = 0.0

    # 실제 계산 시도
    try:
        df['ma5'] = ta.trend.sma_indicator(df['Close'], window=5)
        df['ma20'] = ta.trend.sma_indicator(df['Close'], window=20)
        df['ma60'] = ta.trend.sma_indicator(df['Close'], window=60)
        df['rsi'] = ta.momentum.rsi(df['Close'], window=14)
        
        macd = ta.trend.MACD(df['Close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        bb = ta.volatility.BollingerBands(df['Close'])
        df['bb_h'] = bb.bollinger_hband()
        df['bb_l'] = bb.bollinger_lband()
    except:
        pass # 계산 실패해도 위에서 만든 0.0 값으로 차트는 그려짐

    # NaN 제거
    df = df.fillna(0)
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    trend_score = 0; price_score = 0; timing_score = 0; fund_score = 0
    report = []

    # (1) 추세
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append(f"- ✅ **단기 상승 (+15점)**: 5일선 > 20일선.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append(f"- 🔥 **골든크로스 (+10점)**: 상승 전환 신호!")
    else:
        report.append(f"- 🔻 **단기 하락 (0점)**: 5일선 < 20일선.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append(f"- ✅ **중기 상승 (+5점)**: 60일선 위 안착.")

    # (2) 가격
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 (+15점)**: 반등 기대.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append(f"- ⚠️ **천장권 (0점)**: 조정 주의.")
    else:
        price_score += 5
        report.append(f"- ➖ **중간 지대 (+5점)**: 허리 구간.")

    # (3) 심리
    report.append("\n#### 3️⃣ 투자 심리")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 (RSI {curr['rsi']:.0f}) (+20점)**: 저점 매수 기회.")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 (RSI {curr['rsi']:.0f}) (0점)**: 추격 매수 금지.")
    else:
        timing_score += 5
        report.append(f"- ➖ **안정 (RSI {curr['rsi']:.0f}) (+5점)**: 심리 안정적.")

    # (4) 가치
    report.append("\n#### 4️⃣ 기업 가치")
    if fund_data['Type'] == 'ETF':
        fund_score += 10
        report.append("- ℹ️ **ETF**: 차트와 추세 위주로 분석합니다.")
    else:
        per = fund_data.get('PER', 0)
        pbr = fund_data.get('PBR', 0)
        op = fund_data.get('OperatingProfit', 'N/A')
        
        if per > 0:
            if per < 10: 
                fund_score += 10
                report.append(f"- ✅ **저평가 (PER {per}) (+10점)**")
            elif per > 50:
                 report.append(f"- ⚠️ **고평가 (PER {per}) (0점)**")
            else:
                 fund_score += 5
                 report.append(f"- ➖ **적정 (PER {per}) (+5점)**")
            
            if pbr < 1.0:
                fund_score += 10
                report.append(f"- ✅ **자산주 (PBR {pbr}) (+10점)**")
                
            if "억원" in str(op) and not str(op).startswith("-"):
                 report.append(f"- ✅ **영업이익 흑자**: {op}")
        else:
            report.append("- ℹ️ 재무 정보 부족")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

# ---------------------------------------------------------
# 4. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
st.caption("2중 에러 방지 시스템 탑재")

user_input = st.text_input("🔍 종목 검색 (예: 현대차, 삼성전자, QQQ)", "")

if st.button("분석 시작", type="primary") and user_input:
    search_name = user_input.replace(" ", "").upper()
    found_code = None
    
    # 1. 인기 종목 매핑
    for name, code in TOP_STOCKS.items():
        if search_name == name: found_code = code; break
    if not found_code:
        for name, code in TOP_STOCKS.items():
            if search_name in name and len(search_name) >= 2: found_code = code; search_name = name; break

    # 2. KRX 검색
    if not found_code:
        try:
            listing = fdr.StockListing('KRX')
            res = listing[listing['Name'] == user_input.upper()]
            if res.empty: res = listing[listing['Name'].str.contains(user_input.upper(), na=False)]
            if not res.empty: found_code = res.iloc[0]['Code']; search_name = res.iloc[0]['Name']
        except: pass
    
    if not found_code: found_code = search_name

    # 분석
    st.info(f"🔎 검색 결과: **{search_name}** (코드: {found_code})")

    fund_data = {}
    with st.spinner("재무 데이터 수집 중..."):
        fund_data = get_fundamental_data(found_code)

    with st.spinner("차트 데이터 확보 및 분석 중..."):
        raw_df, err = get_stock_data(found_code)
        
        if err:
            st.error(f"❌ 분석 실패: {err}")
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # 리포트 출력
            st.header(f"📊 {search_name}")
            c1, c2 = st.columns([1, 1.3])
            
            with c1:
                currency = "원" if fund_data['Type'] != 'US' else "$"
                fmt_price = f"{int(curr_price):,}" if currency=="원" else f"{curr_price:.2f}"
                st.metric("현재 주가", f"{fmt_price} {currency}")
                
                st.write(f"### 🤖 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수")
                elif score >= 60: st.info("매수 고려")
                elif score <= 40: st.error("관망/매도")
                else: st.warning("중립")

            with c2:
                st.write("#### 🏢 재무 요약")
                if fund_data['Type'] == 'ETF':
                    st.info("ETF 상품입니다.")
                else:
                    f1, f2 = st.columns(2)
                    f1.metric("영업이익", str(fund_data.get('OperatingProfit', '-')))
                    f1.metric("PER", fund_data.get('PER', 0))
                    f2.metric("ROE", fund_data.get('ROE', '-'))
                    f2.metric("PBR", fund_data.get('PBR', 0))
            
            st.write("---")
            with st.expander("📝 상세 분석 내용 보기", expanded=True):
                for r in report: st.markdown(r)
            
            st.write("---")
            st.subheader("📈 4단 정밀 차트")
            
            # [2차 안전장치] 차트 그리기 전 데이터 검증
            # 만약 위에서 1차 안전장치가 뚫렸더라도 여기서 강제로 0을 채움
            if 'macd_diff' not in df.columns: df['macd_diff'] = 0
            if 'ma20' not in df.columns: df['ma20'] = 0
            if 'ma60' not in df.columns: df['ma60'] = 0
            if 'rsi' not in df.columns: df['rsi'] = 50
            if 'Volume' not in df.columns: df['Volume'] = 0

            # 차트 그리기
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                                row_heights=[0.5, 0.15, 0.15, 0.2],
                                subplot_titles=("주가", "거래량", "MACD", "RSI"))
            
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue', width=1), name='20일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma60'], line=dict(color='green', width=1), name='60일선'), row=1, col=1)
            
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='거래량'), row=2, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['macd_diff'], marker_color='gray', name='MACD'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='purple'), name='RSI'), row=4, col=1)
            
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            
            fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
