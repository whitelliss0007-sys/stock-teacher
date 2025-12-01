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
# 1. [핵심] 대한민국 전 종목 재무 데이터 한번에 가져오기
# ---------------------------------------------------------
@st.cache_data
def get_whole_market_data():
    """KRX 전체 종목의 시세/PER/PBR/배당 정보를 한방에 가져옵니다."""
    try:
        df = fdr.StockListing('KRX')
        # 데이터 정제 (숫자로 변환)
        cols = ['PER', 'PBR', 'DividendYield', 'Change', 'Volume', 'Marcap']
        for col in cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except:
        return pd.DataFrame()

# ---------------------------------------------------------
# 2. 토스 스타일 주식 골라보기 (필터링 로직)
# ---------------------------------------------------------
def get_theme_stocks(theme_name, df):
    """테마 이름을 주면, 그 조건에 맞는 종목 리스트를 반환합니다."""
    filtered = pd.DataFrame()
    
    if theme_name == "💎 저평가 가치주 (싸고 좋은 기업)":
        # PER 10 이하, PBR 1 이하, 시가총액 1천억 이상
        filtered = df[ (df['PER'] > 0) & (df['PER'] < 10) & (df['PBR'] < 1.0) & (df['Marcap'] > 100000000000) ]
        filtered = filtered.sort_values(by='PER', ascending=True) # PER 낮은 순
        
    elif theme_name == "💰 꾸준한 배당주 (은행이자보다 꿀)":
        # 배당수익률 3% 이상, PBR 1.2 이하
        filtered = df[ (df['DividendYield'] >= 3.0) & (df['PBR'] < 1.2) ]
        filtered = filtered.sort_values(by='DividendYield', ascending=False) # 배당 높은 순
        
    elif theme_name == "🔥 급등주 (오늘 거래량 폭발)":
        # 등락률 3% 이상, 거래량 50만주 이상
        filtered = df[ (df['Change'] >= 0.03) & (df['Volume'] > 500000) ]
        filtered = filtered.sort_values(by='Change', ascending=False) # 많이 오른 순
        
    elif theme_name == "🏢 튼튼한 우량주 (대기업)":
        # 시가총액 상위 50위
        filtered = df.sort_values(by='Marcap', ascending=False).head(50)
        
    elif theme_name == "🌱 꿈틀꿈틀 소형주 (PBR 저평가)":
        # 시총 3천억 미만, PBR 0.5 미만 (초저평가)
        filtered = df[ (df['Marcap'] < 300000000000) & (df['PBR'] > 0) & (df['PBR'] < 0.6) ]
        filtered = filtered.sort_values(by='PBR', ascending=True)

    else: # 전체 보기
        filtered = df.head(100) # 너무 많으니 100개만

    return filtered[['Code', 'Name', 'Close', 'Change', 'PER', 'PBR', 'DividendYield']].head(30) # 상위 30개만 리턴

# ---------------------------------------------------------
# 3. 개별 종목 상세 재무 데이터 수집
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'PSR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': '', 'Revenue_Trend': []}
    
    if code.isdigit():
        data['Type'] = 'KR'
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # ETF 여부
            if any(x in soup.select_one('.wrap_company h2 a').text.upper() for x in ['ETF', 'ETN', 'KODEX', 'TIGER', 'ACE']):
                data['Type'] = 'ETF'
                data['Opinion'] = "ℹ️ ETF 상품입니다. (차트 중심 분석)"
                return data

            try: data['PER'] = float(soup.select_one('#_per').text.replace(',', ''))
            except: pass
            try: data['PBR'] = float(soup.select_one('#_pbr').text.replace(',', ''))
            except: pass
            
            try:
                dfs = pd.read_html(resp.text, match='매출액')
                if dfs:
                    df = dfs[-1]
                    op = df[df.iloc[:, 0].str.contains('영업이익', na=False)].iloc[0, -2]
                    data['OperatingProfit'] = f"{op} 억원"
                    roe = df[df.iloc[:, 0].str.contains('ROE', na=False)].iloc[0, -2]
                    data['ROE'] = f"{roe} %"
                    
                    revs = df[df.iloc[:, 0].str.contains('매출액', na=False)].iloc[0, 1:5].tolist()
                    data['Revenue_Trend'] = [str(x) for x in revs if pd.notna(x)]
                    
                    # PSR 계산 (시총은 네이버 상단에서)
                    cap_raw = soup.select_one('#_market_sum').text
                    # 시총 파싱 로직 생략 (약식)
            except: pass
        except: pass
    else:
        # 미국 주식
        data['Type'] = 'US'
        try:
            stock = yf.Ticker(code)
            info = stock.info
            data['PER'] = info.get('trailingPE', 0)
            data['PBR'] = info.get('priceToBook', 0)
            data['PSR'] = info.get('priceToSalesTrailing12Months', 0)
            if info.get('totalRevenue'):
                op = info.get('totalRevenue') * info.get('operatingMargins', 0)
                data['OperatingProfit'] = f"{op/1e9:.2f} B($)"
        except: pass
        
    return data

# ---------------------------------------------------------
# 4. 차트 데이터
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
                    df.columns = df.columns.get_level_values(0)
            except: pass

        df = df.dropna(subset=['Close'])
        if df.empty or len(df) < 60: return None, "데이터 부족"

        df_weekly = df.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        df_monthly = df.resample('M').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        return {'D': df, 'W': df_weekly, 'M': df_monthly}, None
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

    # 1. 추세
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        score += 15
        report.append("- ✅ **단기 상승**: 사는 힘이 더 강해요!")
        if prev['ma5'] <= prev['ma20']:
            score += 10; report.append("- 🔥 **골든크로스**: 이제 막 오르기 시작했어요.")
    else: report.append("- 🔻 **단기 하락**: 파는 힘이 더 세요.")
    if curr['Close'] > curr['ma60']: score += 5; report.append("- ✅ **중기 상승**: 큰 흐름은 좋아요.")

    # 2. 가격
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02: score += 15; report.append("- ✅ **바닥권**: 지금이 쌀 때에요.")
    elif curr['Close'] >= curr['bb_h'] * 0.98: report.append("- ⚠️ **천장권**: 너무 급하게 올랐어요.")
    else: score += 5; report.append("- ➖ **적정 구간**: 무난한 위치에요.")

    # 3. 심리
    report.append("\n#### 3️⃣ 심리 (RSI)")
    if curr['rsi'] < 30: score += 20; report.append("- 🚀 **과매도**: 남들이 공포에 질려 팔 때 사세요.")
    elif curr['rsi'] > 70: report.append("- 😱 **과매수**: 너무 과열됐어요. 조심!")
    else: score += 5; report.append("- ➖ **안정**: 투자 심리가 차분해요.")

    # 4. 가치
    report.append("\n#### 4️⃣ 기업 가치")
    if fund_data['Type'] == 'ETF':
        score += 10; report.append("- ℹ️ **ETF**: 차트가 중요합니다.")
    else:
        per = fund_data.get('PER', 0)
        pbr = fund_data.get('PBR', 0)
        op = fund_data.get('OperatingProfit', 'N/A')
        
        if per > 0 and per < 15: score += 5; report.append(f"- ✅ **저평가 (PER {per})**: 치킨집 본전 뽑는데 {per}년.")
        if pbr > 0 and pbr < 1.2: score += 5; report.append(f"- ✅ **자산주 (PBR {pbr})**: 망해도 본전은 건져요.")
        if "억원" in str(op) and not str(op).startswith("-"): report.append("- ✅ **흑자 기업**: 돈 잘 벌고 있어요.")

    total_score = max(0, min(100, score))
    return total_score, report, df

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 6. 화면 구성 (사이드바 메뉴 + 메인 화면)
# ---------------------------------------------------------
# 전체 데이터 로드
with st.spinner("전체 주식 데이터 로딩 중... (약 5초 소요)"):
    whole_market = get_whole_market_data()

# [사이드바] 주식 골라보기 메뉴
with st.sidebar:
    st.title("📂 주식 골라보기")
    st.write("토스증권처럼 테마별로 찾아보세요!")
    
    selected_theme = st.radio(
        "어떤 주식을 찾으세요?",
        ["🔍 직접 검색", "💎 저평가 가치주 (싸고 좋은 기업)", "💰 꾸준한 배당주 (은행이자보다 꿀)", 
         "🔥 급등주 (오늘 거래량 폭발)", "🏢 튼튼한 우량주 (대기업)", "🌱 꿈틀꿈틀 소형주 (PBR 저평가)"]
    )
    st.info("👆 위 메뉴를 클릭하면 리스트가 바뀝니다.")

st.title("👨‍🏫 AI 주식 과외 선생님")

# [메인 로직]
selected_code = None
selected_name = None

if selected_theme == "🔍 직접 검색":
    search_keyword = st.text_input("종목명 입력 (예: 삼성전자, KODEX, 테슬라)", placeholder="검색어 입력")
    if search_keyword:
        # 전체 리스트에서 검색
        results = whole_market[whole_market['Name'].str.contains(search_keyword, na=False)]
        
        # 결과가 없으면 미국주식이나 ETF API 호출 (기존 방식)
        options = {}
        if not results.empty:
            for i, r in results.head(30).iterrows(): options[f"{r['Name']} ({r['Code']})"] = r['Code']
        
        # 미국주식 티커 추가
        if len(search_keyword) < 6 and search_keyword.isalpha():
            options[f"🇺🇸 미국주식: {search_keyword.upper()}"] = search_keyword.upper()
            
        if options:
            choice = st.selectbox("⬇️ 종목을 선택하세요:", list(options.keys()))
            selected_code = options[choice]
            selected_name = choice.split('(')[0]
            if st.button("분석하기", type="primary"): pass
        else:
            st.warning("검색 결과가 없습니다.")

else: # 테마 선택 시
    st.subheader(f"{selected_theme}")
    filtered_df = get_theme_stocks(selected_theme, whole_market)
    
    if not filtered_df.empty:
        # 데이터프레임 보여주기 (토스 스타일)
        st.dataframe(
            filtered_df[['Name', 'Close', 'Change', 'PER', 'PBR', 'DividendYield']].style.format({
                'Close': '{:,.0f}', 'Change': '{:.2%}', 'PER': '{:.2f}', 'PBR': '{:.2f}', 'DividendYield': '{:.2f}%'
            }), 
            use_container_width=True, 
            height=300
        )
        
        # 리스트에서 선택해서 분석하기
        options = {f"{row['Name']} ({row['Code']})": row['Code'] for idx, row in filtered_df.iterrows()}
        choice = st.selectbox("👉 위 리스트에서 분석할 종목을 고르세요:", list(options.keys()))
        selected_code = options[choice]
        selected_name = choice.split('(')[0]
        
        if st.button("🚀 이 종목 상세 분석하기", type="primary"):
            pass
    else:
        st.error("조건에 맞는 종목이 없습니다.")

# [공통] 분석 실행 파트
if selected_code:
    st.divider()
    
    fund_data = {}
    with st.spinner(f"'{selected_name}' 데이터를 분석하는 중입니다..."):
        fund_data = get_fundamental_data(selected_code)
        data_dict, err = get_stock_data(selected_code)
        
        if err:
            st.error("데이터 부족으로 분석할 수 없습니다.")
        else:
            score, report, df, a = analyze_advanced(data_dict, fund_data) # a는 dummy
            curr_price = df.iloc[-1]['Close']
            
            # 결과 화면
            st.header(f"📊 {selected_name} 분석 결과")
            
            c1, c2 = st.columns([1, 1.3])
            with c1:
                currency = "원" if fund_data['Type'] != 'US' else "$"
                st.metric("현재가", f"{int(curr_price):,} {currency}")
                st.write(f"### 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수 (기회!)")
                elif score >= 60: st.info("매수 고려 (좋음)")
                else: st.warning("관망/매도 (조심)")
                
            with c2:
                st.write("**핵심 재무**")
                st.write(f"- 영업이익: {fund_data.get('OperatingProfit', '-')}")
                st.write(f"- PER(본전): {fund_data.get('PER', '-')}")
                st.write(f"- ROE(실력): {fund_data.get('ROE', '-')}")
            
            with st.expander("📝 상세 분석 리포트 (클릭)", expanded=True):
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
