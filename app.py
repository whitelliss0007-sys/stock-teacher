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
# 1. [필수] 네이버 실시간 검색 (이게 에러 없이 다 찾아줌)
# ---------------------------------------------------------
def search_naver_all_matches(keyword):
    """네이버 증권의 자동완성 API를 통해 주식/ETF를 찾아옵니다."""
    results = []
    try:
        url = f"https://ac.finance.naver.com/ac?q={keyword}&q_enc=euc-kr&st=111&r_format=json&r_enc=euc-kr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if 'items' in data:
            # 0번: 국내, 1번: 해외(있을경우)
            for group in data['items']:
                for item in group:
                    # item[0]:코드, item[1]:이름
                    market = "KR" if item[0].isdigit() else "US"
                    results.append({'Code': item[0], 'Name': item[1], 'Market': market})
    except:
        pass
    return results

# ---------------------------------------------------------
# 2. 시장 전체 데이터 (토스 스타일 필터링용)
# ---------------------------------------------------------
@st.cache_data
def get_whole_market_data():
    """KRX 전체 데이터를 시도하되, 실패하면 빈 데이터프레임 반환 (에러 방지)"""
    try:
        df = fdr.StockListing('KRX')
        cols = ['PER', 'PBR', 'DividendYield', 'Change', 'Volume', 'Marcap']
        for col in cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except:
        # 실패 시 빈 프레임 반환하여 멈춤 방지
        return pd.DataFrame(columns=['Code', 'Name', 'PER', 'PBR', 'DividendYield', 'Change', 'Volume', 'Marcap'])

# ---------------------------------------------------------
# 3. 테마별 필터링 로직
# ---------------------------------------------------------
def get_theme_stocks(theme_name, df):
    if df.empty: return pd.DataFrame()
    
    filtered = pd.DataFrame()
    try:
        if "저평가 가치주" in theme_name:
            filtered = df[(df['PER'] > 0) & (df['PER'] < 10) & (df['PBR'] < 1.0) & (df['Marcap'] > 100000000000)]
            filtered = filtered.sort_values(by='PER')
        elif "배당주" in theme_name:
            filtered = df[(df['DividendYield'] >= 3.0) & (df['PBR'] < 1.2)]
            filtered = filtered.sort_values(by='DividendYield', ascending=False)
        elif "급등주" in theme_name:
            filtered = df[(df['Change'] >= 0.03) & (df['Volume'] > 300000)]
            filtered = filtered.sort_values(by='Change', ascending=False)
        elif "우량주" in theme_name:
            filtered = df.sort_values(by='Marcap', ascending=False).head(50)
        elif "소형주" in theme_name:
            filtered = df[(df['Marcap'] < 300000000000) & (df['PBR'] > 0) & (df['PBR'] < 0.6)]
            filtered = filtered.sort_values(by='PBR')
        else:
            filtered = df.head(50)
    except: pass
    
    if not filtered.empty:
        return filtered[['Code', 'Name', 'Close', 'Change', 'PER', 'PBR', 'DividendYield']].head(30)
    return pd.DataFrame()

# ---------------------------------------------------------
# 4. 재무 데이터 및 차트 데이터 수집
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'PSR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': '', 'Revenue_Trend': []}
    
    # 1. 한국 주식
    if code.isdigit():
        data['Type'] = 'KR'
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ETF 식별
            name_tag = soup.select_one('.wrap_company h2 a')
            stock_name = name_tag.text if name_tag else ""
            if any(x in stock_name.upper() for x in ['ETF', 'ETN', 'KODEX', 'TIGER', 'ACE', 'SOL']):
                data['Type'] = 'ETF'
                data['Opinion'] = "ℹ️ ETF 상품입니다. 차트와 추세를 중심으로 분석합니다."
                return data

            # 기본 지표
            try: data['PER'] = float(soup.select_one('#_per').text.replace(',', ''))
            except: pass
            try: data['PBR'] = float(soup.select_one('#_pbr').text.replace(',', ''))
            except: pass
            
            # 영업이익 등
            try:
                dfs = pd.read_html(response.text, match='매출액')
                if dfs:
                    df = dfs[-1]
                    op = df[df.iloc[:, 0].str.contains('영업이익', na=False)].iloc[0, -2]
                    data['OperatingProfit'] = f"{op} 억원"
                    roe = df[df.iloc[:, 0].str.contains('ROE', na=False)].iloc[0, -2]
                    data['ROE'] = f"{roe} %"
                    
                    revs = df[df.iloc[:, 0].str.contains('매출액', na=False)].iloc[0, 1:5].tolist()
                    data['Revenue_Trend'] = [str(x) for x in revs if pd.notna(x)]
                    
                    # PSR 약식 계산 (현재가*주식수 / 최근매출) - 생략하거나 시총기반 계산 가능
            except: pass
        except: pass

    # 2. 미국 주식
    else:
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

        # 주/월봉
        df_w = df.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        df_m = df.resample('M').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        return {'D': df, 'W': df_w, 'M': df_m}, None
    except Exception as e: return None, str(e)

# ---------------------------------------------------------
# 5. 분석 로직 (치킨집 비유)
# ---------------------------------------------------------
def analyze_advanced(data_dict, fund_data):
    df = data_dict['D'].copy()
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
    score = 0; report = []

    # 분석 멘트
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        score += 15; report.append("- ✅ **단기 상승**: 사는 힘이 더 셉니다.")
        if prev['ma5'] <= prev['ma20']: score += 10; report.append("- 🔥 **골든크로스**: 상승 출발 신호!")
    else: report.append("- 🔻 **단기 하락**: 파는 힘이 더 셉니다.")
    if curr['Close'] > curr['ma60']: score += 5; report.append("- ✅ **중기 상승**: 3개월 추세가 좋습니다.")

    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02: score += 15; report.append("- ✅ **바닥권**: 지금이 쌀 때입니다.")
    elif curr['Close'] >= curr['bb_h'] * 0.98: report.append("- ⚠️ **천장권**: 너무 급하게 올랐습니다.")
    else: score += 5; report.append("- ➖ **적정 구간**: 무난한 위치입니다.")

    report.append("\n#### 3️⃣ 심리")
    if curr['rsi'] < 30: score += 20; report.append("- 🚀 **과매도**: 공포에 살 기회입니다.")
    elif curr['rsi'] > 70: report.append("- 😱 **과매수**: 과열됐습니다. 추격 매수 금지.")
    else: score += 5; report.append("- ➖ **안정**: 심리가 차분합니다.")

    report.append("\n#### 4️⃣ 가치")
    if fund_data['Type'] == 'ETF':
        score += 10; report.append("- ℹ️ **ETF**: 차트와 수급 위주로 분석합니다.")
    else:
        per = fund_data.get('PER', 0)
        pbr = fund_data.get('PBR', 0)
        op = str(fund_data.get('OperatingProfit', ''))
        
        if per > 0 and per < 15: score += 5; report.append(f"- ✅ **저평가 (PER {per})**: 치킨집 본전 뽑는데 {per}년.")
        if pbr > 0 and pbr < 1.2: score += 5; report.append(f"- ✅ **자산주 (PBR {pbr})**: 망해도 본전은 건집니다.")
        if "억원" in op and not op.startswith("-"): report.append("- ✅ **흑자 기업**: 돈 잘 벌고 있습니다.")

    return max(0, min(100, score)), report, df

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 6. 화면 구성 (토스 스타일 메뉴 + 만능 검색)
# ---------------------------------------------------------
# 데이터 로드 (실패해도 괜찮음, 검색은 네이버가 해주니까)
with st.spinner("데이터 준비 중..."):
    whole_market = get_whole_market_data()

with st.sidebar:
    st.title("📂 주식 골라보기")
    selected_theme = st.radio(
        "메뉴 선택",
        ["🔍 직접 검색", "💎 저평가 가치주", "💰 꾸준한 배당주", "🔥 급등주", "🏢 튼튼한 우량주", "🌱 꿈틀꿈틀 소형주"]
    )

st.title("👨‍🏫 AI 주식 과외 선생님")

selected_code = None
selected_name = None

# [1] 직접 검색 (네이버 연동)
if selected_theme == "🔍 직접 검색":
    search_keyword = st.text_input("종목명/ETF 입력 (예: KODEX, 반도체, 펩트론, 테슬라)", placeholder="검색어 입력")
    
    if search_keyword:
        # 여기서 네이버 API를 호출하여 목록을 가져옴 (KeyError 해결!)
        search_results = search_naver_all_matches(search_keyword)
        
        if search_results:
            options = {f"[{item['Market']}] {item['Name']} ({item['Code']})": item['Code'] for item in search_results}
            
            choice = st.selectbox("⬇️ 종목을 선택하세요:", list(options.keys()))
            selected_code = options[choice]
            selected_name = choice.split('(')[0]
            
            if st.button("🚀 분석하기", type="primary"): pass
        else:
            st.error("검색 결과가 없습니다. (미국 주식은 티커로 입력해보세요)")

# [2] 테마별 보기 (토스 스타일)
else:
    st.subheader(f"{selected_theme}")
    if not whole_market.empty:
        filtered_df = get_theme_stocks(selected_theme, whole_market)
        if not filtered_df.empty:
            st.dataframe(
                filtered_df[['Name', 'Close', 'Change', 'PER', 'PBR', 'DividendYield']].style.format({
                    'Close': '{:,.0f}', 'Change': '{:.2%}', 'PER': '{:.2f}', 'PBR': '{:.2f}', 'DividendYield': '{:.2f}%'
                }), use_container_width=True
            )
            # 리스트에서 선택
            options = {f"{row['Name']} ({row['Code']})": row['Code'] for idx, row in filtered_df.iterrows()}
            choice = st.selectbox("👉 분석할 종목 선택:", list(options.keys()))
            selected_code = options[choice]
            selected_name = choice.split('(')[0]
            if st.button("🚀 상세 분석하기", type="primary"): pass
        else:
            st.info("조건에 맞는 종목이 없거나 데이터를 불러오지 못했습니다.")
    else:
        st.warning("현재 서버 연결 문제로 '골라보기 리스트'를 불러올 수 없습니다. '직접 검색' 기능을 이용해주세요! (검색은 정상 작동합니다)")

# [3] 공통 분석 실행
if selected_code:
    st.divider()
    with st.spinner(f"'{selected_name}' 분석 중..."):
        fund_data = get_fundamental_data(selected_code)
        data_dict, err = get_stock_data(selected_code)
        
        if err:
            st.error("데이터 부족으로 분석할 수 없습니다.")
        else:
            score, report, df, a = analyze_advanced(data_dict, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # 결과 헤더
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
                st.write("**핵심 재무**")
                st.write(f"- 영업이익: {fund_data.get('OperatingProfit', '-')}")
                st.write(f"- PER: {fund_data.get('PER', '-')}")
                st.write(f"- ROE: {fund_data.get('ROE', '-')}")
            
            with st.expander("📝 상세 분석 리포트", expanded=True):
                for r in report: st.markdown(r)
            
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
