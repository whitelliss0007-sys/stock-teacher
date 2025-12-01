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
import re

st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")

# ---------------------------------------------------------
# 0. [필수] 테마별 추천 종목 (서버 차단 방어용 내장 리스트)
# ---------------------------------------------------------
THEME_STOCKS = {
    "💎 저평가 가치주 (싸고 좋은 기업)": [
        {'Code': '000270', 'Name': '기아'}, {'Code': '005930', 'Name': '삼성전자'},
        {'Code': '012330', 'Name': '현대모비스'}, {'Code': '000810', 'Name': '삼성화재'},
        {'Code': '055550', 'Name': '신한지주'}, {'Code': '086790', 'Name': '하나금융지주'},
        {'Code': '004020', 'Name': '현대제철'}, {'Code': '010950', 'Name': 'S-Oil'}
    ],
    "💰 꾸준한 배당주 (은행이자보다 꿀)": [
        {'Code': '105560', 'Name': 'KB금융'}, {'Code': '030200', 'Name': 'KT'},
        {'Code': '017670', 'Name': 'SK텔레콤'}, {'Code': '033780', 'Name': 'KT&G'},
        {'Code': '316140', 'Name': '우리금융지주'}, {'Code': '071050', 'Name': '한국금융지주'}
    ],
    "🔥 급등/성장 기대주": [
        {'Code': '086520', 'Name': '에코프로'}, {'Code': '247540', 'Name': '에코프로비엠'},
        {'Code': '000660', 'Name': 'SK하이닉스'}, {'Code': '042700', 'Name': '한미반도체'},
        {'Code': '196170', 'Name': '알테오젠'}, {'Code': '012450', 'Name': '한화에어로스페이스'},
        {'Code': '277810', 'Name': '레인보우로보틱스'}, {'Code': '028300', 'Name': 'HLB'}
    ],
    "🏢 튼튼한 우량주 (대기업)": [
        {'Code': '005380', 'Name': '현대차'}, {'Code': '373220', 'Name': 'LG에너지솔루션'},
        {'Code': '207940', 'Name': '삼성바이오로직스'}, {'Code': '005490', 'Name': 'POSCO홀딩스'},
        {'Code': '035420', 'Name': 'NAVER'}, {'Code': '006400', 'Name': '삼성SDI'},
        {'Code': '051910', 'Name': 'LG화학'}, {'Code': '035720', 'Name': '카카오'}
    ]
}

# ---------------------------------------------------------
# 1. 네이버 실시간 검색 (만능 검색기)
# ---------------------------------------------------------
def search_naver_stocks(keyword):
    try:
        url = f"https://ac.finance.naver.com/ac?q={keyword}&q_enc=euc-kr&st=111&r_format=json&r_enc=euc-kr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers)
        data = resp.json()
        results = []
        if 'items' in data:
            for group in data['items']:
                for item in group:
                    code = item[0]
                    name = item[1]
                    market = "KR" if code.isdigit() else "US"
                    results.append({'Code': code, 'Name': name, 'Market': market})
        return results
    except: return []

# ---------------------------------------------------------
# 2. 재무 데이터 수집
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'PSR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': '', 'Revenue_Trend': []}
    
    if code.isdigit():
        data['Type'] = 'KR'
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ETF 식별
            try:
                name = soup.select_one('.wrap_company h2 a').text
                if any(x in name.upper() for x in ['ETF', 'ETN', 'KODEX', 'TIGER', 'ACE', 'SOL']):
                    data['Type'] = 'ETF'
                    data['Opinion'] = "ℹ️ ETF 상품입니다. (차트/수급 위주 분석)"
            except: pass

            try: data['PER'] = float(soup.select_one('#_per').text.replace(',', ''))
            except: pass
            try: data['PBR'] = float(soup.select_one('#_pbr').text.replace(',', ''))
            except: pass
            
            if data['Type'] != 'ETF':
                try:
                    dfs = pd.read_html(response.text, match='매출액')
                    if dfs:
                        fin_df = dfs[-1]
                        op = fin_df[fin_df.iloc[:, 0].str.contains('영업이익', na=False)].iloc[0, -2]
                        data['OperatingProfit'] = f"{op} 억원"
                        roe = fin_df[fin_df.iloc[:, 0].str.contains('ROE', na=False)].iloc[0, -2]
                        data['ROE'] = f"{roe} %"
                        
                        revs = fin_df[fin_df.iloc[:, 0].str.contains('매출액', na=False)].iloc[0, 1:5].tolist()
                        data['Revenue_Trend'] = [str(x) for x in revs if pd.notna(x)]
                except: pass
        except: pass

    else: # 미국 주식
        data['Type'] = 'US'
        try:
            stock = yf.Ticker(code)
            info = stock.info
            if info.get('quoteType') == 'ETF': data['Type'] = 'ETF'
            data['PER'] = info.get('trailingPE', 0)
            data['PBR'] = info.get('priceToBook', 0)
            data['PSR'] = info.get('priceToSalesTrailing12Months', 0)
            if info.get('totalRevenue'):
                op = info.get('totalRevenue') * info.get('operatingMargins', 0)
                data['OperatingProfit'] = f"{op/1e9:.2f} B($)"
        except: pass
    return data

# ---------------------------------------------------------
# 3. 차트 데이터
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
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            except: pass

        df = df.dropna(subset=['Close'])
        if df.empty or len(df) < 60: return None, "데이터 부족"

        df_w = df.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        df_m = df.resample('M').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        return {'D': df, 'W': df_w, 'M': df_m}, None
    except Exception as e: return None, str(e)

# ---------------------------------------------------------
# 4. 분석 로직 (치킨집 비유 + 7개 값 반환)
# ---------------------------------------------------------
def analyze_advanced(data_dict, fund_data):
    df = data_dict['D'].copy()
    # 안전장치
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
        trend_score += 15; report.append("- ✅ **단기 상승 (+15점)**: 5일선 > 20일선. 매수세 우위.")
        if prev['ma5'] <= prev['ma20']: trend_score += 10; report.append("- 🔥 **골든크로스 (+10점)**: 상승 출발!")
    else: report.append("- 🔻 **단기 하락 (0점)**: 5일선 < 20일선.")
    if curr['Close'] > curr['ma60']: trend_score += 5; report.append("- ✅ **중기 상승 (+5점)**: 60일선 위.")

    # 2. 가격
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02: price_score += 15; report.append("- ✅ **바닥권 (+15점)**: 반등 기대.")
    elif curr['Close'] >= curr['bb_h'] * 0.98: report.append("- ⚠️ **천장권 (0점)**: 조정 주의.")
    else: price_score += 5; report.append("- ➖ **중간 지대 (+5점)**")

    # 3. 심리
    report.append("\n#### 3️⃣ 투자 심리")
    if curr['rsi'] < 30: timing_score += 20; report.append("- 🚀 **과매도 (+20점)**: 공포에 살 기회.")
    elif curr['rsi'] > 70: report.append("- 😱 **과매수 (0점)**: 과열 상태.")
    else: timing_score += 5; report.append("- ➖ **안정 (+5점)**")

    # 4. 가치
    report.append("\n#### 4️⃣ 기업 가치")
    if fund_data['Type'] == 'ETF' or fund_data['Type'] == 'US':
        fund_score += 10; report.append("- ℹ️ **ETF/해외**: 차트 위주 분석.")
    else:
        per = fund_data.get('PER', 0); pbr = fund_data.get('PBR', 0); op = str(fund_data.get('OperatingProfit', ''))
        
        if per > 0 and per < 15: fund_score += 5; report.append(f"- ✅ **저평가 (PER {per})**: 치킨집 본전 뽑는데 {per}년.")
        elif per > 50: report.append("- ⚠️ **고평가**: 미래 기대감 반영.")
        else: fund_score += 5; report.append("- ➖ **적정**: 적정한 가격.")
        
        if pbr > 0 and pbr < 1.2: fund_score += 5; report.append("- ✅ **자산주**: 망해도 본전 건짐.")
        if "억원" in op and not op.startswith("-"): report.append("- ✅ **흑자**: 돈 잘 벌고 있음.")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    
    # [중요] 여기서 7개 값을 반환합니다!
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 5. 화면 구성 (사이드바 + 메인)
# ---------------------------------------------------------
# [사이드바 메뉴]
with st.sidebar:
    st.title("📂 주식 골라보기")
    st.write("토스증권 스타일 메뉴")
    selected_theme = st.radio(
        "메뉴를 선택하세요",
        ["🔍 직접 검색"] + list(THEME_STOCKS.keys())
    )

st.title("👨‍🏫 AI 주식 과외 선생님")

selected_code = None
selected_name = None

# [1] 직접 검색 로직
if selected_theme == "🔍 직접 검색":
    search_keyword = st.text_input("종목명/ETF 입력", placeholder="삼성전자, KODEX, 테슬라...")
    if search_keyword:
        # 네이버 API 검색
        naver_res = search_naver_stocks(search_keyword.strip())
        options = {}
        for item in naver_res:
            options[f"[{item['Market']}] {item['Name']} ({item['Code']})"] = item['Code']
        
        # 미국 티커 추가
        if len(search_keyword) < 6 and search_keyword.isalpha():
            options[f"[US] 미국주식: {search_keyword.upper()}"] = search_keyword.upper()
            
        if options:
            choice = st.selectbox("⬇️ 종목 선택:", list(options.keys()))
            selected_code = options[choice]
            selected_name = choice.split('(')[0]
            if st.button("🚀 분석하기", type="primary"): pass
        else:
            st.error("검색 결과가 없습니다.")

# [2] 테마별 골라보기 로직
else:
    st.subheader(f"{selected_theme}")
    stock_list = THEME_STOCKS[selected_theme]
    
    # 리스트박스 생성
    options = {f"{s['Name']} ({s['Code']})": s['Code'] for s in stock_list}
    choice = st.selectbox("👉 종목을 선택하세요:", list(options.keys()))
    
    selected_code = options[choice]
    selected_name = choice.split('(')[0]
    
    if st.button("🚀 상세 분석하기", type="primary"): pass

# [3] 공통 분석 실행 (에러 났던 부분 수정됨!)
if selected_code:
    st.divider()
    with st.spinner(f"'{selected_name}' 분석 중..."):
        fund_data = get_fundamental_data(selected_code)
        data_dict, err = get_stock_data(selected_code)
        
        if err:
            st.error("데이터 부족")
        else:
            # [수정 완료] 이제 여기서 7개 값을 정상적으로 받습니다.
            score, report, df, ts, ps, tis, fs = analyze_advanced(data_dict, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # 결과 표시
            st.header(f"📊 {selected_name}")
            c1, c2 = st.columns([1, 1.3])
            with c1:
                currency = "원" if fund_data['Type'] != 'US' else "$"
                st.metric("현재가", f"{int(curr_price):,} {currency}")
                st.write(f"### 🤖 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수")
                elif score >= 60: st.info("매수 고려")
                elif score <= 40: st.error("관망/매도")
                else: st.warning("중립")
                
            with c2:
                st.write("**핵심 점수표**")
                st.write(f"📈 추세: {ts}/30  |  📉 가격: {ps}/20")
                st.write(f"⏱️ 심리: {tis}/30  |  💰 가치: {fs}/20")
                st.write("---")
                st.write(f"- 영업이익: {fund_data.get('OperatingProfit', '-')}")
                st.write(f"- PER: {fund_data.get('PER', '-')}")
            
            with st.expander("📝 상세 분석 내용 보기", expanded=True):
                for r in report: st.markdown(r)
            
            # 차트
            tab1, tab2 = st.tabs(["일봉", "주봉"])
            def draw_chart(df):
                df = sanitize_for_chart(df)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue'), name='20일선'), row=1, col=1)
                fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='거래량'), row=2, col=1)
                fig.update_layout(height=500, xaxis_rangeslider_visible=False, showlegend=False)
                return fig

            with tab1: st.plotly_chart(draw_chart(data_dict['D']), use_container_width=True)
            with tab2: st.plotly_chart(draw_chart(data_dict['W']), use_container_width=True)
