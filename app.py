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
# 1. 대한민국 전 종목 리스트 가져오기 (캐싱)
# ---------------------------------------------------------
@st.cache_data
def get_krx_list():
    try:
        # 한국거래소(KRX)의 모든 종목(ETF 포함) 다운로드
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name']] # 코드와 이름만 남김
    except:
        return pd.DataFrame(columns=['Code', 'Name'])

# ---------------------------------------------------------
# 2. 재무 데이터 수집 (네이버/야후)
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': ''}
    
    # [한국 주식]
    if code.isdigit():
        data['Type'] = 'KR'
        # ETF 식별 (이름에 ETF 관련 단어가 있거나 코드로 식별)
        # 여기서는 간단히 코드로 넘어온 데이터를 분석
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
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
            if info.get('returnOnEquity'):
                data['ROE'] = f"{info.get('returnOnEquity')*100:.2f} %"
            
            if info.get('totalRevenue') and info.get('operatingMargins'):
                op_val = info.get('totalRevenue') * info.get('operatingMargins')
                data['OperatingProfit'] = f"{op_val / 1000000000:.2f} B ($)"
        except: pass
        
    return data

# ---------------------------------------------------------
# 3. 차트 데이터 (안전장치 강화)
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2)
        
        # 1차: FinanceDataReader (한국)
        try:
            if code.isdigit():
                # 한국 주식은 코드로 바로 시도 or .KS/.KQ
                df = fdr.DataReader(code, start, end)
            else:
                # 미국 주식
                df = fdr.DataReader(code, start, end)
        except:
            df = pd.DataFrame()

        # 2차: Yahoo Finance (비상용 & 미국주식)
        if df.empty or len(df) < 10:
            try:
                # 한국 주식은 .KS 붙여서 시도
                yf_ticker = f"{code}.KS" if code.isdigit() else code
                df = yf.download(yf_ticker, start=start, end=end, progress=False)
                
                # 코스닥(.KQ) 재시도
                if df.empty and code.isdigit():
                    df = yf.download(f"{code}.KQ", start=start, end=end, progress=False)

                if isinstance(df.columns, pd.MultiIndex):
                    try: df.columns = df.columns.get_level_values(0)
                    except: pass
            except: pass

        df = df.dropna(subset=['Close'])
        if df.empty or len(df) < 60: return None, "데이터 로딩 실패"
        return df, None
    except Exception as e: return None, str(e)

# ---------------------------------------------------------
# 4. 상세 분석 로직
# ---------------------------------------------------------
def analyze_advanced(df, fund_data):
    # [1차 안전장치] 컬럼 초기화
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

    # (1) 추세
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append(f"- ✅ **단기 상승 (+15점)**: 5일선 > 20일선.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append(f"- 🔥 **골든크로스 (+10점)**: 상승 신호!")
    else:
        report.append(f"- 🔻 **단기 하락 (0점)**: 5일선 < 20일선.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append(f"- ✅ **중기 상승 (+5점)**: 60일선 위.")

    # (2) 가격
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 (+15점)**: 반등 기대.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append(f"- ⚠️ **천장권 (0점)**: 조정 주의.")
    else:
        price_score += 5
        report.append(f"- ➖ **중간 지대 (+5점)**")

    # (3) 심리
    report.append("\n#### 3️⃣ 투자 심리")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 (RSI {curr['rsi']:.0f}) (+20점)**: 저점 매수 기회.")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 (RSI {curr['rsi']:.0f}) (0점)**: 과열 상태.")
    else:
        timing_score += 5
        report.append(f"- ➖ **안정 (RSI {curr['rsi']:.0f}) (+5점)**")

    # (4) 가치
    report.append("\n#### 4️⃣ 기업 가치")
    # ETF거나 미국 주식이거나 재무정보가 없으면 제외
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
            report.append("- ℹ️ 재무 정보 부족 (점수 제외)")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 5. 화면 구성 (검색 엔진 방식)
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
st.caption("한국 전 종목(ETF 포함) + 미국 주식 검색 지원")

# 1. 데이터 로드 (KRX 전체)
with st.spinner("한국거래소 전 종목 리스트 불러오는 중... (최초 1회만 느림)"):
    krx_list = get_krx_list()

# 2. 검색 인터페이스
col1, col2 = st.columns([3, 1])
with col1:
    search_keyword = st.text_input("🔍 종목명 입력 (예: 반도체, 효성, 삼성, ORCL)", placeholder="찾고 싶은 종목이나 키워드를 입력하세요")

selected_code = None
selected_name = None

# 3. 검색 로직
if search_keyword:
    search_keyword = search_keyword.upper().strip()
    
    # [A] 한국 종목 검색 (이름에 키워드가 포함된 모든 종목 찾기)
    # 예: '반도체' -> 삼성전자, SK하이닉스, TIGER 반도체, KODEX 반도체 등등
    results = krx_list[krx_list['Name'].str.contains(search_keyword, na=False)]
    
    # [B] 미국 주식 직접 입력 처리 (결과가 없거나 영어인 경우)
    # 사용자가 'ORCL' 같이 티커를 직접 입력했을 때를 대비
    is_us_ticker = len(search_keyword) < 6 and search_keyword.isalpha()
    
    # 옵션 생성
    options = {}
    
    # 1. 한국 주식 검색 결과 추가
    if not results.empty:
        for index, row in results.iterrows():
            display_text = f"{row['Name']} ({row['Code']})"
            options[display_text] = row['Code']
    
    # 2. 미국 주식(티커) 직접 입력 옵션 추가
    if is_us_ticker:
        options[f"🇺🇸 미국주식: {search_keyword}"] = search_keyword

    # 4. 선택 상자 표시
    if options:
        selected_option = st.selectbox("⬇️ 분석할 종목을 선택하세요:", list(options.keys()))
        selected_code = options[selected_option]
        selected_name = selected_option.split('(')[0].strip() # 이름만 추출
        
        # 분석 버튼
        if st.button("🚀 선택한 종목 분석하기", type="primary"):
            pass # 아래 로직 실행
    else:
        st.warning("검색 결과가 없습니다. 정확한 종목명이나 티커를 입력해주세요.")

# ---------------------------------------------------------
# 6. 분석 실행 (선택된 종목이 있을 때만)
# ---------------------------------------------------------
if selected_code:
    st.divider()
    st.info(f"선택된 종목: **{selected_name}** (코드: {selected_code}) 분석을 시작합니다.")
    
    fund_data = {}
    with st.spinner("재무 데이터 수집 중..."):
        fund_data = get_fundamental_data(selected_code)

    with st.spinner("차트 데이터 분석 중..."):
        raw_df, err = get_stock_data(selected_code)
        
        if err:
            st.error(f"❌ 데이터 로딩 실패: {err}")
            st.write("해당 종목의 데이터가 없거나, 일시적인 서버 오류일 수 있습니다.")
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # 리포트 출력
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
                if "ETF" in selected_name or "KODEX" in selected_name or "TIGER" in selected_name:
                    st.info("ETF 상품입니다. (차트 위주 분석)")
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
