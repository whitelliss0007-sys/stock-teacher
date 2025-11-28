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
# 0. 인기 종목 매핑 (이름 -> 코드)
# ---------------------------------------------------------
# 여기에 없는 종목도 검색되지만, 여기에 적어두면 100% 정확하게 찾습니다.
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
    # 미국 및 ETF
    "테슬라": "TSLA", "애플": "AAPL", "엔비디아": "NVDA", "마이크로소프트": "MSFT",
    "구글": "GOOGL", "아마존": "AMZN", "QQQ": "QQQ", "SPY": "SPY", "SOXL": "SOXL",
    "TIGER 2차전지": "305540", "KODEX 200": "069500"
}

# ---------------------------------------------------------
# 1. 재무 데이터 (네이버/야후)
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {
        'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 
        'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': ''
    }
    
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
            
            # 시가총액
            try:
                cap_text = soup.select_one('#_market_sum').text
                parts = cap_text.split('조')
                trillion = int(parts[0].replace(',', '').strip()) * 1000000000000
                billion = int(parts[1].replace(',', '').strip()) * 100000000 if len(parts) > 1 else 0
                data['Marcap'] = trillion + billion
            except: pass

            # 영업이익 & ROE (테이블 크롤링)
            try:
                dfs = pd.read_html(response.text, match='매출액')
                if dfs:
                    fin_df = dfs[-1]
                    target_col = -2 # 최근 확정 실적
                    
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
            if info.get('returnOnEquity'):
                data['ROE'] = f"{info.get('returnOnEquity')*100:.2f} %"
            
            # 영업이익
            if info.get('totalRevenue') and info.get('operatingMargins'):
                op_val = info.get('totalRevenue') * info.get('operatingMargins')
                data['OperatingProfit'] = f"{op_val / 1000000000:.2f} B ($)"
        except: pass
        
    return data

# ---------------------------------------------------------
# 2. 차트 데이터
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        # 안전장치: 한글이 들어오면 에러 처리 (야후 404 방지)
        if any(ord(c) > 127 for c in str(code)): 
            return None, "종목 코드를 찾지 못했습니다. (한글 입력됨)"

        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2)
        
        ticker = f"{code}.KS" if code.isdigit() else code
        df = fdr.DataReader(ticker, start, end)
        
        if (df.empty or len(df) < 10) and code.isdigit():
             df = fdr.DataReader(f"{code}.KQ", start, end)
        
        if df.empty: # 미국 주식 등
             df = yf.download(code, start=start, end=end, progress=False)
             if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 60: return None, "데이터 부족"
        return df, None
    except Exception as e: return None, str(e)

# ---------------------------------------------------------
# 3. 상세 분석 로직 (설명 강화)
# ---------------------------------------------------------
def analyze_advanced(df, fund_data):
    df['ma5'] = ta.trend.sma_indicator(df['Close'], window=5)
    df['ma20'] = ta.trend.sma_indicator(df['Close'], window=20)
    df['ma60'] = ta.trend.sma_indicator(df['Close'], window=60)
    df['rsi'] = ta.momentum.rsi(df['Close'], window=14)
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    trend_score = 0; price_score = 0; timing_score = 0; fund_score = 0
    report = []

    # (1) 추세
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append(f"- ✅ **단기 상승 (+15점)**: 최근 5일 평균 가격이 20일 평균보다 높습니다. 단기적으로 사는 힘이 더 셉니다.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append(f"- 🔥 **골든크로스 (+10점)**: 5일선이 20일선을 돌파했습니다. 상승 초입일 가능성이 큽니다.")
    else:
        report.append(f"- 🔻 **단기 하락 (0점)**: 5일 평균 가격이 20일 평균보다 낮습니다. 파는 힘이 더 셉니다.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append(f"- ✅ **중기 상승 (+5점)**: 60일선(수급선) 위에 있습니다. 3개월 추세가 살아있습니다.")

    # (2) 가격 위치 (볼린저밴드)
    bb_l = ta.volatility.bollinger_lband(df['Close'])
    bb_h = ta.volatility.bollinger_hband(df['Close'])
    curr_l = bb_l.iloc[-1]
    curr_h = bb_h.iloc[-1]
    
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr_l * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 (+15점)**: 주가가 밴드 하단에 닿았습니다. 통계적으로 반등할 확률이 높습니다.")
    elif curr['Close'] >= curr_h * 0.98:
        report.append(f"- ⚠️ **천장권 (0점)**: 주가가 밴드 상단에 닿았습니다. 단기 과열로 조정받을 수 있습니다.")
    else:
        price_score += 5
        report.append(f"- ➖ **중간 지대 (+5점)**: 허리 구간입니다.")

    # (3) 심리 (RSI)
    report.append("\n#### 3️⃣ 투자 심리")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 (RSI {curr['rsi']:.0f}) (+20점)**: 공포 구간입니다. 남들이 팔 때 살 기회입니다.")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 (RSI {curr['rsi']:.0f}) (0점)**: 탐욕 구간입니다. 너무 많이 올랐으니 추격 매수는 자제하세요.")
    else:
        timing_score += 5
        report.append(f"- ➖ **중립 (RSI {curr['rsi']:.0f}) (+5점)**: 심리가 안정적입니다.")

    # (4) 기업 가치 (재무제표 평가)
    report.append("\n#### 4️⃣ 기업 평가 (재무)")
    if fund_data['Type'] == 'ETF':
        fund_score += 10
        report.append("- ℹ️ **ETF**: 재무 지표 대신 구성 종목과 차트가 중요합니다.")
    else:
        per = fund_data.get('PER', 0)
        pbr = fund_data.get('PBR', 0)
        op = fund_data.get('OperatingProfit', 'N/A')
        
        if per > 0:
            if per < 10: 
                fund_score += 10
                report.append(f"- ✅ **저평가 (PER {per}) (+10점)**: 이익 대비 주가가 쌉니다. (기준 10 이하)")
            elif per > 50:
                 report.append(f"- ⚠️ **고성장/고평가 (PER {per}) (0점)**: 현재 이익보다 미래 기대감이 큽니다. 성장성이 꺾이면 위험합니다.")
            else:
                 fund_score += 5
                 report.append(f"- ➖ **적정 (PER {per}) (+5점)**: 적정한 수준입니다.")
            
            if pbr < 1.0:
                fund_score += 10
                report.append(f"- ✅ **자산주 (PBR {pbr}) (+10점)**: 회사가 가진 재산보다 주가가 쌉니다.")
                
            if "억원" in str(op) and not str(op).startswith("-"):
                 report.append(f"- ✅ **영업이익 흑자**: {op}. 본업에서 돈을 잘 벌고 있습니다.")
        else:
            report.append("- ℹ️ 재무 정보 부족 (점수 제외)")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

# ---------------------------------------------------------
# 4. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
st.caption("재무제표 정밀 분석 + 명확한 매매 조언")

user_input = st.text_input("🔍 종목 검색 (예: 현대차, 삼성전자, 애플, QQQ)", "")

if st.button("분석 시작", type="primary") and user_input:
    # 1. 종목 코드 찾기 (강력한 검색 로직)
    search_name = user_input.replace(" ", "").upper()
    found_code = None
    
    # [1단계] 인기 종목 매핑 (현대차 -> 005380)
    for name, code in TOP_STOCKS.items():
        if search_name == name: 
            found_code = code; break
            
    # [2단계] 한국거래소 리스트 검색
    if not found_code:
        try:
            listing = fdr.StockListing('KRX')
            # 정확히 일치
            res = listing[listing['Name'] == user_input.upper()]
            if res.empty: 
                # 포함 (현대 -> 현대차, 현대모비스 등)
                res = listing[listing['Name'].str.contains(user_input.upper(), na=False)]
            
            if not res.empty:
                found_code = res.iloc[0]['Code']
                search_name = res.iloc[0]['Name']
        except: pass
    
    # [3단계] 그래도 없으면 입력값을 코드로 간주
    if not found_code: found_code = search_name

    # 디버깅 정보 (사용자에게 코드를 보여줌)
    st.info(f"🔎 검색 결과: **{search_name}** (코드: {found_code})")

    # 2. 데이터 수집
    fund_data = {}
    with st.spinner("재무제표(영업이익, PER) 뜯어오는 중..."):
        fund_data = get_fundamental_data(found_code)

    with st.spinner("차트 정밀 분석 중..."):
        raw_df, err = get_stock_data(found_code)
        
        if err:
            st.error(f"❌ 분석 실패: {err}")
            st.warning("종목명이 정확한지 확인해주세요. (한글은 코드로 변환되어야 합니다)")
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # --- 리포트 출력 ---
            st.header(f"📊 {search_name}")
            c1, c2 = st.columns([1, 1.3])
            
            with c1:
                currency = "원" if fund_data['Type'] != 'US' else "$"
                fmt_price = f"{int(curr_price):,}" if currency=="원" else f"{curr_price:.2f}"
                st.metric("현재 주가", f"{fmt_price} {currency}")
                
                st.write(f"### 🤖 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수 (기회를 잡으세요)")
                elif score >= 60: st.info("매수 고려 (긍정적)")
                elif score <= 40: st.error("관망/매도 (위험)")
                else: st.warning("중립 (대기)")

            with c2:
                st.write("#### 🏢 기업 재무 건강검진")
                if fund_data['Type'] == 'ETF':
                    st.info("ETF 상품입니다. 구성 종목과 추세가 중요합니다.")
                else:
                    f1, f2 = st.columns(2)
                    op_val = fund_data.get('OperatingProfit', '-')
                    if op_val == 'N/A' or op_val is None: op_val = '-'
                    
                    f1.metric("영업이익", str(op_val))
                    f1.metric("PER (저평가)", fund_data.get('PER', 0))
                    f2.metric("ROE (수익성)", fund_data.get('ROE', '-'))
                    f2.metric("PBR (자산가치)", fund_data.get('PBR', 0))
                    
                    if "흑자" in str(fund_data.get('Opinion')):
                        st.success("✅ 영업이익 흑자 기업입니다.")
            
            st.write("---")
            st.subheader("📝 선생님의 상세 분석 내용")
            with st.expander("여기를 눌러서 자세한 설명을 읽어보세요", expanded=True):
                for r in report: st.markdown(r)
            
            st.write("---")
            st.subheader("📈 4단 정밀 차트")
            
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
