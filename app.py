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
import json

st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")

# ---------------------------------------------------------
# 1. [핵심] 네이버에서 대한민국 모든 ETF 명단 가져오기
# ---------------------------------------------------------
@st.cache_data
def get_all_korean_etfs():
    """네이버 증권 API를 통해 현재 상장된 모든 ETF 리스트를 가져옵니다."""
    try:
        url = "https://finance.naver.com/api/sise/etfItemList.nhn"
        resp = requests.get(url)
        data = resp.json()
        
        # 데이터프레임으로 변환
        etf_list = pd.DataFrame(data['result']['etfItemList'])
        etf_list = etf_list[['itemcode', 'itemname']]
        etf_list.columns = ['Code', 'Name']
        return etf_list
    except:
        return pd.DataFrame()

# ---------------------------------------------------------
# 2. [핵심] 대한민국 일반 주식(코스피/코스닥) 가져오기
# ---------------------------------------------------------
@st.cache_data
def get_krx_stocks():
    """서버 차단 대비: 주요 대형주 내장 + 라이브 시도"""
    # 비상용 내장 데이터 (대형주 위주)
    manual_data = [
        {'Code': '005930', 'Name': '삼성전자'}, {'Code': '000660', 'Name': 'SK하이닉스'},
        {'Code': '373220', 'Name': 'LG에너지솔루션'}, {'Code': '207940', 'Name': '삼성바이오로직스'},
        {'Code': '005380', 'Name': '현대차'}, {'Code': '000270', 'Name': '기아'},
        {'Code': '068270', 'Name': '셀트리온'}, {'Code': '005490', 'Name': 'POSCO홀딩스'},
        {'Code': '035420', 'Name': 'NAVER'}, {'Code': '035720', 'Name': '카카오'},
        {'Code': '298020', 'Name': '효성중공업'}, {'Code': '004800', 'Name': '효성'}
    ]
    df_manual = pd.DataFrame(manual_data)

    try:
        df_live = fdr.StockListing('KRX')
        if not df_live.empty:
            return df_live[['Code', 'Name']]
    except: pass
    
    return df_manual

# ---------------------------------------------------------
# 3. 통합 검색 리스트 생성
# ---------------------------------------------------------
@st.cache_data
def get_combined_list():
    # 1. 일반 주식
    stocks = get_krx_stocks()
    # 2. 모든 ETF (ACE, SOL, KBSTAR 포함 800개+)
    etfs = get_all_korean_etfs()
    
    # 합치기
    combined = pd.concat([stocks, etfs], ignore_index=True)
    return combined.drop_duplicates(subset=['Code'])

# ---------------------------------------------------------
# 4. 재무 데이터 수집
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': ''}
    
    if code.isdigit():
        data['Type'] = 'KR'
        # ETF 확인: 이름에 ETF 브랜드가 포함되어 있는지 확인
        # (전체 리스트를 로드하는 것은 비효율적이므로 분석 단계에서 확인)
        
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ETF 여부 판단 (네이버 페이지 내 'ETF' 태그 확인)
            if "ETF" in soup.text or "ETN" in soup.text:
                 data['Type'] = 'ETF'
                 data['Opinion'] = "ℹ️ ETF/ETN 상품입니다. 영업이익/PER 분석 대신 차트와 추세를 참고하세요."
                 # ETF라도 시가총액은 가져옴
                 try:
                    cap_text = soup.select_one('#_market_sum').text
                    parts = cap_text.split('조')
                    trillion = int(parts[0].replace(',', '').strip()) * 1000000000000
                    billion = int(parts[1].replace(',', '').strip()) * 100000000 if len(parts) > 1 else 0
                    data['Marcap'] = trillion + billion
                 except: pass
                 return data

            # 일반 주식 데이터 크롤링
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
# 5. 차트 데이터 (안전장치)
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*3)
        try:
            if code.isdigit(): df = fdr.DataReader(code, start, end)
            else: df = fdr.DataReader(code, start, end)
        except: df = pd.DataFrame()

        if df.empty or len(df) < 10:
            try:
                yf_ticker = f"{code}.KS" if code.isdigit() else code
                df = yf.download(yf_ticker, start=start, end=end, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    try: df.columns = df.columns.get_level_values(0)
                    except: pass
            except: pass

        df = df.dropna(subset=['Close'])
        if df.empty or len(df) < 60: return None, "데이터 로딩 실패"
        return df, None
    except Exception as e: return None, str(e)

# ---------------------------------------------------------
# 6. 분석 로직
# ---------------------------------------------------------
def analyze_advanced(df, fund_data):
    for col in ['ma5', 'ma20', 'ma60', 'rsi', 'macd', 'macd_signal', 'macd_diff', 'bb_h', 'bb_l']:
        if col not in df.columns: df[col] = 0.0

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
    except: pass

    df = df.fillna(0)
    curr = df.iloc[-1]; prev = df.iloc[-2]
    
    trend_score = 0; price_score = 0; timing_score = 0; fund_score = 0
    report = []

    # 1. 추세
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append("- ✅ **단기 상승 (+15점)**: 5일선 > 20일선. 매수세 우위.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append("- 🔥 **골든크로스 (+10점)**: 상승 전환 신호!")
    else:
        report.append("- 🔻 **단기 하락 (0점)**: 5일선 < 20일선.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append("- ✅ **중기 상승 (+5점)**: 60일선 위 안착.")

    # 2. 가격
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append("- ✅ **바닥권 (+15점)**: 반등 기대.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append("- ⚠️ **천장권 (0점)**: 조정 주의.")
    else:
        price_score += 5
        report.append("- ➖ **중간 지대 (+5점)**")

    # 3. 심리
    report.append("\n#### 3️⃣ 투자 심리")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 (RSI {curr['rsi']:.0f}) (+20점)**: 저점 매수 기회.")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 (RSI {curr['rsi']:.0f}) (0점)**: 과열 상태.")
    else:
        timing_score += 5
        report.append(f"- ➖ **안정 (RSI {curr['rsi']:.0f}) (+5점)**")

    # 4. 가치
    report.append("\n#### 4️⃣ 기업 가치")
    if fund_data['Type'] == 'ETF' or fund_data['Type'] == 'US':
        fund_score += 10
        report.append("- ℹ️ **ETF/해외주식**: 차트와 추세 위주로 분석합니다.")
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

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 7. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
st.caption("ACE, SOL, KBSTAR 포함 전 종목 검색 지원")

# 1. 데이터 로드 (모든 ETF + 주식)
with st.spinner("대한민국 모든 주식과 ETF 명단을 불러오는 중입니다..."):
    combined_list = get_combined_list()

# 2. 검색창
search_keyword = st.text_input("종목명/ETF 입력 (예: ACE, 반도체, 효성, ORCL)", placeholder="찾고 싶은 종목을 입력하세요")

selected_code = None
selected_name = None

# 3. 검색 로직
if search_keyword:
    search_keyword = search_keyword.upper().strip()
    
    # [A] 한국 종목 검색 (전체 리스트에서 검색)
    results = combined_list[combined_list['Name'].str.contains(search_keyword, na=False)]
    
    # [B] 미국 주식 티커 처리
    is_us_ticker = len(search_keyword) < 6 and search_keyword.isalpha()
    
    options = {}
    if not results.empty:
        # 상위 100개만 표시
        for index, row in results.head(100).iterrows():
            options[f"{row['Name']} ({row['Code']})"] = row['Code']
    
    if is_us_ticker:
        options[f"🇺🇸 미국주식: {search_keyword}"] = search_keyword

    if options:
        selected_option = st.selectbox("⬇️ 검색 결과 중 하나를 선택하세요:", list(options.keys()))
        selected_code = options[selected_option]
        selected_name = selected_option.split('(')[0].strip()
        
        if st.button("🚀 선택한 종목 분석하기", type="primary"):
            pass
    else:
        st.error("검색 결과가 없습니다.")

# ---------------------------------------------------------
# 8. 분석 실행
# ---------------------------------------------------------
if selected_code:
    st.divider()
    st.info(f"선택된 종목: **{selected_name}** (코드: {selected_code})")
    
    fund_data = {}
    with st.spinner("재무 데이터 수집 중..."):
        fund_data = get_fundamental_data(selected_code)

    with st.spinner("차트 데이터 분석 중..."):
        raw_df, err = get_stock_data(selected_code)
        
        if err:
            st.error(f"데이터 로딩 실패: {err}")
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            st.header(f"📊 {selected_name}")
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
                if "ETF" in str(fund_data['Type']) or "ETF" in str(fund_data.get('Opinion')):
                    st.info("ETF 상품입니다. (차트/수급 분석)")
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
            
            df = sanitize_for_chart(df)
            
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.15, 0.2], subplot_titles=("주가", "거래량", "MACD", "RSI"))
            
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
