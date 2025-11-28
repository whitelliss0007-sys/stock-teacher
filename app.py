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
import yfinance as yf  # 미국 주식용 필수

st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")

# ---------------------------------------------------------
# 0. 인기 종목 하드코딩
# ---------------------------------------------------------
TOP_STOCKS = {
    # 한국 코스피/코스닥
    "삼성전자": "005930", "SK하이닉스": "000660", "LG에너지솔루션": "373220",
    "현대차": "005380", "카카오": "035720", "NAVER": "035420", "에코프로": "086520",
    "POSCO홀딩스": "005490", "셀트리온": "068270", "삼성SDI": "006400",
    # 한국 ETF
    "KODEX 200": "069500", "KODEX 레버리지": "122630", "KODEX 인버스": "114800",
    "TIGER 2차전지": "305540", "TIGER 미국테크TOP10": "360750",
    # 미국 주식 (티커)
    "테슬라": "TSLA", "애플": "AAPL", "엔비디아": "NVDA", "마이크로소프트": "MSFT",
    "구글": "GOOGL", "아마존": "AMZN", "QQQ": "QQQ", "SPY": "SPY", "SOXL": "SOXL"
}

# ---------------------------------------------------------
# 1. 재무 데이터 가져오기 (한국:네이버 / 미국:야후)
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {
        'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 
        'OperatingProfit': 'N/A', 'Opinion': '', 'Type': 'Stock'
    }
    
    # [A] 한국 주식 (숫자 코드) -> 네이버 크롤링
    if code.isdigit():
        data['Type'] = 'KR_Stock'
        # ETF 감지
        if any(x in code for x in ['069500', '122630', '252670', '114800']): # 주요 ETF 예외처리
            data['Type'] = 'ETF'
            data['Opinion'] = "ℹ️ ETF는 기업이 아니므로 영업이익/PER 분석을 하지 않습니다."
            return data
            
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')

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

            # 영업이익 (표 크롤링)
            try:
                dfs = pd.read_html(response.text, match='매출액')
                if dfs:
                    fin_df = dfs[-1]
                    target_col = -2
                    
                    op_row = fin_df[fin_df.iloc[:, 0].str.contains('영업이익', na=False)]
                    if not op_row.empty: data['OperatingProfit'] = str(op_row.iloc[0, target_col]) + " 억원"
                    
                    roe_row = fin_df[fin_df.iloc[:, 0].str.contains('ROE', na=False)]
                    if not roe_row.empty: data['ROE'] = str(roe_row.iloc[0, target_col]) + " %"
            except: pass
        except: pass

    # [B] 미국 주식 (문자 티커) -> 야후 파이낸스
    else:
        data['Type'] = 'US_Stock'
        try:
            stock = yf.Ticker(code)
            info = stock.info
            data['PER'] = info.get('trailingPE', 0)
            data['PBR'] = info.get('priceToBook', 0)
            data['Marcap'] = info.get('marketCap', 0)
            data['ROE'] = f"{info.get('returnOnEquity', 0)*100:.2f} %" if info.get('returnOnEquity') else 'N/A'
            
            # 영업이익 (달러 -> 원화 대략적 표시는 생략하거나 달러로 표시)
            op_prof = info.get('operatingMargins', 0) * info.get('totalRevenue', 0)
            if op_prof:
                data['OperatingProfit'] = f"{op_prof / 1000000000:.2f} B ($)"
                
            # 미국 ETF 감지 (QQQ, SPY 등은 PER이 없을 수 있음)
            if info.get('quoteType') == 'ETF':
                data['Type'] = 'ETF'
                data['Opinion'] = "ℹ️ ETF 상품입니다. (구성 종목의 집합)"
        except: pass

    # 의견 생성 (주식인 경우에만)
    if data['Type'] != 'ETF':
        opinions = []
        if data['PER'] > 0 and data['PER'] < 15: opinions.append("✅ 저평가 (PER 15↓)")
        if data['PBR'] > 0 and data['PBR'] < 1.0: opinions.append("✅ 자산가치 우수 (PBR 1↓)")
        if "억원" in str(data['OperatingProfit']) and not str(data['OperatingProfit']).startswith("-"):
             opinions.append("✅ 영업이익 흑자")
        data['Opinion'] = " / ".join(opinions) if opinions else "⚠️ 중립/판단 보류"

    return data

# ---------------------------------------------------------
# 2. 차트 데이터 가져오기
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2)
        
        # 한국 주식은 .KS 붙이기 / 미국은 그대로
        ticker = f"{code}.KS" if code.isdigit() else code
        
        df = fdr.DataReader(ticker, start, end)
        # 한국인데 데이터 없으면 코스닥(.KQ) 시도
        if (df.empty or len(df) < 10) and code.isdigit():
             df = fdr.DataReader(f"{code}.KQ", start, end)
        
        if df.empty: return None, "데이터 없음"
        return df, None
    except Exception as e: return None, str(e)

def analyze_advanced(df, fund_data):
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
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    trend_score = 0; price_score = 0; timing_score = 0; fund_score = 0
    report = []

    # 1. 추세
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append(f"- ✅ **단기 상승 (+15점)**: 5일선 > 20일선")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append(f"- 🔥 **골든크로스 (+10점)**: 매수 신호 발생")
    else:
        report.append(f"- 🔻 **단기 하락 (0점)**")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append(f"- ✅ **중기 상승 (+5점)**")

    # 2. 가격
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 (+15점)**: 반등 기대")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append(f"- ⚠️ **천장권 (0점)**: 조정 주의")
    else:
        price_score += 5
        report.append(f"- ➖ **중간 (+5점)**")

    # 3. 타이밍
    report.append("\n#### 3️⃣ 심리 (RSI)")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 (RSI {curr['rsi']:.0f}) (+20점)**: 저점 매수 기회")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 (RSI {curr['rsi']:.0f}) (0점)**: 과열 상태")
    else:
        timing_score += 5
        report.append(f"- ➖ **중립 (RSI {curr['rsi']:.0f}) (+5점)**")

    # 4. 가치 (ETF는 제외)
    report.append("\n#### 4️⃣ 가치 (펀더멘털)")
    if fund_data['Type'] == 'ETF':
        report.append("- ℹ️ **ETF**: 가치 평가 점수 제외 (차트 위주 분석)")
        # ETF는 가치 점수 만점을 0으로 처리하여 총점에 영향 안 주게 하거나, 기본 점수 부여
        # 여기서는 총점 계산 시 분모를 조정하는 게 복잡하므로, 기본 점수를 줌
        fund_score += 10 
    else:
        per = fund_data.get('PER', 0)
        pbr = fund_data.get('PBR', 0)
        if per > 0:
            if per < 15: 
                fund_score += 10
                report.append(f"- ✅ **저평가 (PER {per:.1f}) (+10점)**")
            elif per < 30:
                fund_score += 5
                report.append(f"- ➖ **적정 (PER {per:.1f}) (+5점)**")
            else:
                report.append(f"- ⚠️ **고평가 (PER {per:.1f}) (0점)**")
                
            if pbr < 1.0:
                fund_score += 10
                report.append(f"- ✅ **자산가치 우수 (PBR {pbr:.1f}) (+10점)**")
        else:
             report.append("- ℹ️ 재무 데이터 부족")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

# ---------------------------------------------------------
# 3. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님 (Global Ver.)")
st.caption("한국/미국 주식 + ETF 완벽 지원")

user_input = st.text_input("🔍 종목 검색 (예: 삼성전자, 애플, TIGER 2차전지, TSLA)", "")

if st.button("분석 시작", type="primary") and user_input:
    search_name = user_input.replace(" ", "").upper()
    found_code = None
    
    # 1. 인기 종목 매핑
    for name, code in TOP_STOCKS.items():
        if search_name == name or (len(search_name) >= 2 and search_name in name):
            found_code = code; search_name = name; break
            
    # 2. 검색 (인기 종목에 없으면)
    if not found_code:
        # 한글이면 KRX 검색
        if any(ord(c) > 127 for c in user_input):
            try:
                listing = fdr.StockListing('KRX')
                res = listing[listing['Name'].str.contains(user_input.upper(), na=False)]
                if not res.empty: found_code = res.iloc[0]['Code']; search_name = res.iloc[0]['Name']
            except: pass
        else:
            # 영어면 바로 티커로 간주
            found_code = search_name

    if not found_code: found_code = search_name

    # 3. 데이터 가져오기
    fund_data = {}
    with st.spinner("데이터 수집 중... (네이버/야후)"):
        fund_data = get_fundamental_data(found_code)

    with st.spinner("차트 분석 중..."):
        raw_df, err = get_stock_data(found_code)
        
        if err:
            st.error(f"데이터를 찾을 수 없습니다: {err}")
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # 상단 요약
            st.divider()
            st.header(f"📊 {search_name}")
            
            c1, c2 = st.columns([1, 1.5])
            with c1:
                # 가격 표시 (한국:원 / 미국:달러)
                currency = "원" if fund_data['Type'] != 'US_Stock' else "$"
                fmt_price = f"{int(curr_price):,}" if currency=="원" else f"{curr_price:.2f}"
                st.metric("현재 주가", f"{fmt_price} {currency}")
                
                st.write(f"### 🤖 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수")
                elif score >= 60: st.info("매수 고려")
                else: st.warning("관망/매도")
                
                st.info(f"💡 {fund_data['Opinion']}")

            with c2:
                st.write("#### 🏢 기업/펀드 정보")
                if fund_data['Type'] == 'ETF':
                    st.warning("📊 **ETF 상품입니다.**\n\n영업이익/PER 같은 기업 지표 대신, 차트 추세와 거래량을 중심으로 분석했습니다.")
                else:
                    f1, f2 = st.columns(2)
                    op_val = fund_data.get('OperatingProfit', '-')
                    if op_val == 'N/A' or op_val is None: op_val = '-'
                    
                    f1.metric("영업이익", op_val)
                    f1.metric("PER", fund_data.get('PER', 0))
                    f2.metric("ROE", fund_data.get('ROE', '-'))
                    f2.metric("PBR", fund_data.get('PBR', 0))

            # 차트 & 리포트
            st.write("---")
            with st.expander("📝 상세 분석 내용 보기", expanded=True):
                for r in report: st.markdown(r)

            st.subheader("📈 4단 정밀 차트")
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.15, 0.2])
            
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue', width=1), name='20일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_l'], line=dict(color='gray', width=0), name='BB'), row=1, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='거래량'), row=2, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['macd_diff'], marker_color='gray', name='MACD'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='purple'), name='RSI'), row=4, col=1)
            
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            
            fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
