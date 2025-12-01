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
# 0. [필수] 테마별 추천 종목 (토스 스타일 메뉴 데이터)
# ---------------------------------------------------------
# 서버 데이터가 막혔을 때를 대비해 미리 분류해둔 알짜 종목들입니다.
THEME_DATA = {
    "📈 연속 상승세 (인기)": [
        {'Code': '000660', 'Name': 'SK하이닉스', 'Desc': 'AI 반도체 대장주'},
        {'Code': '042700', 'Name': '한미반도체', 'Desc': 'HBM 장비 대장'},
        {'Code': '196170', 'Name': '알테오젠', 'Desc': '바이오 플랫폼 대장'},
        {'Code': '012450', 'Name': '한화에어로스페이스', 'Desc': 'K-방산 수출 호조'},
        {'Code': '277810', 'Name': '레인보우로보틱스', 'Desc': '삼성전자 로봇 파트너'},
        {'Code': '086520', 'Name': '에코프로', 'Desc': '2차전지 대장주'}
    ],
    "💎 저평가 성장주 (싸고 좋은)": [
        {'Code': '000270', 'Name': '기아', 'Desc': 'PER 3배, 역대급 실적'},
        {'Code': '005380', 'Name': '현대차', 'Desc': '글로벌 판매량 호조'},
        {'Code': '004020', 'Name': '현대제철', 'Desc': 'PBR 0.2배, 절대 저평가'},
        {'Code': '011200', 'Name': 'HMM', 'Desc': '해운 운임 상승 수혜'},
        {'Code': '010950', 'Name': 'S-Oil', 'Desc': '고배당 정유주'},
        {'Code': '005930', 'Name': '삼성전자', 'Desc': '국민주식, 반등 기대'}
    ],
    "💰 꾸준한 배당주 (연금처럼)": [
        {'Code': '105560', 'Name': 'KB금융', 'Desc': '대표 은행주, 주주환원'},
        {'Code': '055550', 'Name': '신한지주', 'Desc': '고배당 금융지주'},
        {'Code': '030200', 'Name': 'KT', 'Desc': '통신주, 안정적 배당'},
        {'Code': '033780', 'Name': 'KT&G', 'Desc': '담배 인삼, 고배당'},
        {'Code': '017670', 'Name': 'SK텔레콤', 'Desc': '통신 대장주'},
        {'Code': '000810', 'Name': '삼성화재', 'Desc': '보험 대장주'}
    ],
    "🏢 ETF 모아보기 (지수/테마)": [
        {'Code': '069500', 'Name': 'KODEX 200', 'Desc': '대한민국 대표 지수'},
        {'Code': '360750', 'Name': 'TIGER 미국필라델피아반도체', 'Desc': '미국 반도체 투자'},
        {'Code': '371460', 'Name': 'TIGER 차이나전기차', 'Desc': '중국 전기차 밸류체인'},
        {'Code': '411420', 'Name': 'ACE 미국S&P500', 'Desc': '미국 시장 전체 투자'},
        {'Code': '438560', 'Name': 'SOL 미국배당다우존스', 'Desc': '월배당 인기 ETF'}
    ]
}

# ---------------------------------------------------------
# 1. [핵심] 검색 및 데이터 수집 함수들
# ---------------------------------------------------------
def search_naver_stocks(keyword):
    """네이버 실시간 검색 연동"""
    try:
        url = f"https://ac.finance.naver.com/ac?q={keyword}&q_enc=euc-kr&st=111&r_format=json&r_enc=euc-kr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers)
        data = resp.json()
        results = []
        if 'items' in data:
            for group in data['items']:
                for item in group:
                    market = "KR" if item[0].isdigit() else "US"
                    results.append({'Code': item[0], 'Name': item[1], 'Market': market})
        return results
    except: return []

def get_fundamental_data(code):
    """재무 데이터 수집 (ETF/일반 구분)"""
    data = {'PER': 0, 'PBR': 0, 'PSR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': '', 'Revenue_Trend': []}
    
    if code.isdigit(): # 한국
        data['Type'] = 'KR'
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            soup = BeautifulSoup(requests.get(url, headers=headers).text, 'html.parser')
            
            name = soup.select_one('.wrap_company h2 a').text
            if any(x in name.upper() for x in ['ETF', 'ETN', 'KODEX', 'TIGER', 'ACE', 'SOL']):
                data['Type'] = 'ETF'
                data['Opinion'] = "ℹ️ ETF 상품입니다. (차트 위주 분석)"
                return data

            # 일반 주식 데이터
            try: data['PER'] = float(soup.select_one('#_per').text.replace(',', ''))
            except: pass
            try: data['PBR'] = float(soup.select_one('#_pbr').text.replace(',', ''))
            except: pass
            
            try:
                dfs = pd.read_html(str(soup), match='매출액')
                if dfs:
                    df = dfs[-1]
                    op = df[df.iloc[:, 0].str.contains('영업이익', na=False)].iloc[0, -2]
                    data['OperatingProfit'] = f"{op} 억원"
                    revs = df[df.iloc[:, 0].str.contains('매출액', na=False)].iloc[0, 1:5].tolist()
                    data['Revenue_Trend'] = [str(x) for x in revs if pd.notna(x)]
            except: pass
        except: pass
    else: # 미국
        data['Type'] = 'US'
        try:
            stock = yf.Ticker(code)
            info = stock.info
            if info.get('quoteType') == 'ETF': data['Type'] = 'ETF'
            data['PER'] = info.get('trailingPE', 0)
            data['PBR'] = info.get('priceToBook', 0)
        except: pass
    return data

@st.cache_data
def get_stock_data(code):
    """차트 데이터 수집 (안전장치 포함)"""
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2)
        
        if code.isdigit():
            df = fdr.DataReader(code, start, end)
            if df.empty: df = fdr.DataReader(f"{code}.KS", start, end)
            if df.empty: df = fdr.DataReader(f"{code}.KQ", start, end)
        else:
            df = fdr.DataReader(code, start, end)
            if df.empty: 
                df = yf.download(code, start=start, end=end, progress=False)
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        df = df.dropna(subset=['Close'])
        if df.empty or len(df) < 60: return None, "데이터 부족"

        df_w = df.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        return {'D': df, 'W': df_w}, None
    except Exception as e: return None, str(e)

def analyze_advanced(data_dict, fund_data):
    """상세 분석 로직"""
    df = data_dict['D'].copy()
    # 컬럼 안전장치
    for col in ['ma5', 'ma20', 'ma60', 'rsi', 'macd', 'bb_l']: 
        if col not in df.columns: df[col] = 0.0
    
    try:
        df['ma5'] = ta.trend.sma_indicator(df['Close'], 5)
        df['ma20'] = ta.trend.sma_indicator(df['Close'], 20)
        df['ma60'] = ta.trend.sma_indicator(df['Close'], 60)
        df['rsi'] = ta.momentum.rsi(df['Close'], 14)
        df['bb_l'] = ta.volatility.bollinger_lband(df['Close'])
        df['bb_h'] = ta.volatility.bollinger_hband(df['Close'])
    except: pass
    
    df = df.fillna(0)
    curr = df.iloc[-1]; prev = df.iloc[-2]
    score = 0; report = []

    # 1. 추세
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        score += 15; report.append("- ✅ **단기 상승**: 사는 힘이 셉니다.")
        if prev['ma5'] <= prev['ma20']: score += 10; report.append("- 🔥 **골든크로스**: 상승 출발!")
    else: report.append("- 🔻 **단기 하락**: 파는 힘이 셉니다.")
    
    # 2. 가격
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02: score += 15; report.append("- ✅ **바닥권**: 쌉니다.")
    else: score += 5; report.append("- ➖ **적정 구간**: 무난합니다.")

    # 3. 가치
    report.append("\n#### 3️⃣ 기업 가치")
    if fund_data['Type'] == 'ETF':
        score += 10; report.append("- ℹ️ **ETF**: 차트가 중요합니다.")
    else:
        per = fund_data.get('PER', 0)
        if per > 0 and per < 15: score += 10; report.append("- ✅ **저평가**: 돈 잘 벌고 쌉니다.")
        elif per > 50: report.append("- ⚠️ **고평가**: 미래 기대감이 큽니다.")
        else: score += 5; report.append("- ➖ **적정**: 적당한 가격입니다.")

    return max(0, min(100, score)), report, df

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 5. 화면 구성 (토스 스타일 사이드바 + 메인)
# ---------------------------------------------------------
# [사이드바] 메뉴 구성
with st.sidebar:
    st.title("📂 주식 골라보기")
    st.write("원하는 테마를 선택하세요!")
    
    menu_options = ["🔍 직접 검색"] + list(THEME_DATA.keys())
    selected_menu = st.radio("메뉴 목록", menu_options)

st.title("👨‍🏫 AI 주식 과외 선생님")

selected_code = None
selected_name = None

# [1] 직접 검색 모드
if selected_menu == "🔍 직접 검색":
    st.caption("종목명/ETF를 입력하면 찾아드립니다.")
    search_keyword = st.text_input("검색어 입력", placeholder="삼성전자, KODEX, 테슬라...")
    
    if search_keyword:
        # 네이버 검색 연동
        naver_res = search_naver_stocks(search_keyword)
        options = {}
        
        # 검색 결과 매핑
        for item in naver_res:
            options[f"[{item['Market']}] {item['Name']} ({item['Code']})"] = item['Code']
        
        # 미국 티커 추가
        if len(search_keyword) < 6 and search_keyword.isalpha():
            options[f"[US] 미국주식: {search_keyword.upper()}"] = search_keyword.upper()

        if options:
            choice = st.selectbox("⬇️ 종목을 선택하세요:", list(options.keys()))
            selected_code = options[choice]
            
            # 이름 추출 (보기 좋게)
            if ']' in choice: selected_name = choice.split(']')[1].split('(')[0].strip()
            else: selected_name = choice
            
            if st.button("🚀 분석하기", type="primary"): pass
        else:
            st.warning("검색 결과가 없습니다.")

# [2] 테마별 리스트 모드 (토스 스타일)
else:
    st.subheader(f"{selected_menu}")
    st.write("AI가 엄선한 관련 종목들입니다.")
    
    # 해당 테마의 종목 가져오기
    stock_list = THEME_DATA[selected_menu]
    
    # 리스트 형태로 보여주기 (데이터프레임)
    df_theme = pd.DataFrame(stock_list)
    st.dataframe(
        df_theme[['Name', 'Code', 'Desc']].rename(columns={'Name':'종목명', 'Code':'코드', 'Desc':'특징'}),
        use_container_width=True,
        hide_index=True
    )
    
    # 선택 박스
    options = {f"{s['Name']} ({s['Code']})": s['Code'] for s in stock_list}
    choice = st.selectbox("👉 분석할 종목을 선택하세요:", list(options.keys()))
    
    selected_code = options[choice]
    selected_name = choice.split('(')[0]
    
    if st.button("🚀 상세 분석 시작", type="primary"): pass

# [3] 공통 분석 실행 화면
if selected_code:
    st.divider()
    with st.spinner(f"'{selected_name}' 데이터를 분석 중입니다..."):
        fund_data = get_fundamental_data(selected_code)
        data_dict, err = get_stock_data(selected_code)
        
        if err:
            st.error("데이터 부족으로 분석할 수 없습니다.")
        else:
            score, report, df, a = analyze_advanced(data_dict, fund_data) # a는 dummy
            curr_price = df.iloc[-1]['Close']
            
            # 결과 헤더
            st.header(f"📊 {selected_name} 분석 결과")
            
            c1, c2 = st.columns([1, 1.3])
            with c1:
                currency = "원" if fund_data['Type'] != 'US' else "$"
                st.metric("현재가", f"{int(curr_price):,} {currency}")
                st.write(f"### 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수")
                elif score >= 60: st.info("매수 고려")
                else: st.warning("관망/매도")
                
            with c2:
                st.write("#### 🏢 핵심 지표")
                f1, f2 = st.columns(2)
                f1.metric("영업이익", str(fund_data.get('OperatingProfit', '-')))
                f1.metric("PER", fund_data.get('PER', 0))
                
                if fund_data.get('Revenue_Trend'):
                    st.caption(f"매출 추이: {' -> '.join(fund_data['Revenue_Trend'])}")
            
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
