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
# 0. [필수] 내장 코드북 (주요 종목 빠른 검색용)
# ---------------------------------------------------------
STATIC_STOCKS = [
    {'Code': '005930', 'Name': '삼성전자'}, {'Code': '000660', 'Name': 'SK하이닉스'},
    {'Code': '373220', 'Name': 'LG에너지솔루션'}, {'Code': '207940', 'Name': '삼성바이오로직스'},
    {'Code': '005380', 'Name': '현대차'}, {'Code': '000270', 'Name': '기아'},
    {'Code': '068270', 'Name': '셀트리온'}, {'Code': '005490', 'Name': 'POSCO홀딩스'},
    {'Code': '035420', 'Name': 'NAVER'}, {'Code': '035720', 'Name': '카카오'},
    {'Code': '006400', 'Name': '삼성SDI'}, {'Code': '051910', 'Name': 'LG화학'},
    {'Code': '086520', 'Name': '에코프로'}, {'Code': '247540', 'Name': '에코프로비엠'},
    {'Code': '069500', 'Name': 'KODEX 200'}, {'Code': '122630', 'Name': 'KODEX 레버리지'},
    {'Code': '252670', 'Name': 'KODEX 200선물인버스2X'}, {'Code': '114800', 'Name': 'KODEX 인버스'},
    {'Code': '360750', 'Name': 'TIGER 미국필라델피아반도체나스닥'}, {'Code': '371460', 'Name': 'TIGER 차이나전기차SOLACTIVE'},
]

# ---------------------------------------------------------
# 1. [핵심] 네이버 실시간 검색 (검색창 연동)
# ---------------------------------------------------------
def search_naver_stock_code(keyword):
    """
    사용자가 입력한 키워드를 네이버 증권 검색창에 대신 물어보고
    정확한 종목 코드와 이름을 받아옵니다. (펩트론, 잡주, 신규상장주 모두 해결)
    """
    try:
        # 네이버 자동완성 API 호출
        url = f"https://ac.finance.naver.com/ac?q={keyword}&q_enc=euc-kr&st=111&r_format=json&r_enc=euc-kr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        data = response.json()
        
        # 결과 파싱
        results = []
        if 'items' in data and len(data['items']) > 0:
            for item in data['items'][0]:
                # item[0]: 코드, item[1]: 종목명
                results.append({'Code': item[0], 'Name': item[1]})
        return results
    except:
        return []

# ---------------------------------------------------------
# 2. [핵심] 모든 ETF 명단 가져오기
# ---------------------------------------------------------
@st.cache_data
def get_all_korean_etfs():
    try:
        url = "https://finance.naver.com/api/sise/etfItemList.nhn"
        resp = requests.get(url)
        data = resp.json()
        etf_list = pd.DataFrame(data['result']['etfItemList'])
        return etf_list[['itemcode', 'itemname']].rename(columns={'itemcode': 'Code', 'itemname': 'Name'})
    except:
        return pd.DataFrame()

# ---------------------------------------------------------
# 3. 재무 데이터 수집
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': '', 'Revenue_Trend': [], 'PSR': 0}
    
    if code.isdigit():
        data['Type'] = 'KR'
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ETF/ETN 여부 확인 (이름이나 태그로)
            stock_name = ""
            try: stock_name = soup.select_one('.wrap_company h2 a').text
            except: pass
            
            # ETF 판단 로직 강화
            if 'ETF' in stock_name or 'ETN' in stock_name or 'KODEX' in stock_name or 'TIGER' in stock_name or 'ACE' in stock_name:
                data['Type'] = 'ETF'
                data['Opinion'] = "ℹ️ ETF 상품입니다. (기업 분석 제외)"
            
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

            if data['Type'] != 'ETF':
                try:
                    dfs = pd.read_html(response.text, match='매출액')
                    if dfs:
                        fin_df = dfs[-1]
                        op_row = fin_df[fin_df.iloc[:, 0].str.contains('영업이익', na=False)]
                        if not op_row.empty: data['OperatingProfit'] = f"{op_row.iloc[0, -2]} 억원"
                        roe_row = fin_df[fin_df.iloc[:, 0].str.contains('ROE', na=False)]
                        if not roe_row.empty: data['ROE'] = f"{roe_row.iloc[0, -2]} %"
                        
                        rev_row = fin_df[fin_df.iloc[:, 0].str.contains('매출액', na=False)]
                        if not rev_row.empty:
                            recent_revs = rev_row.iloc[0, 1:5].tolist()
                            data['Revenue_Trend'] = [str(x) for x in recent_revs if pd.notna(x)]
                            last_rev_str = str(recent_revs[-1]).replace(',', '')
                            if last_rev_str.replace('.', '', 1).isdigit():
                                last_rev = float(last_rev_str) * 100000000
                                if last_rev > 0 and data['Marcap'] > 0:
                                    data['PSR'] = round(data['Marcap'] / last_rev, 2)
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
            data['PSR'] = info.get('priceToSalesTrailing12Months', 0)
            if info.get('returnOnEquity'): data['ROE'] = f"{info.get('returnOnEquity')*100:.2f} %"
            if info.get('totalRevenue') and info.get('operatingMargins'):
                op_val = info.get('totalRevenue') * info.get('operatingMargins')
                data['OperatingProfit'] = f"{op_val / 1000000000:.2f} B ($)"
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
                    try: df.columns = df.columns.get_level_values(0)
                    except: pass
            except: pass

        df = df.dropna(subset=['Close'])
        if df.empty or len(df) < 60: return None, "데이터 부족"

        df_weekly = df.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        df_monthly = df.resample('M').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})

        return {'D': df, 'W': df_weekly, 'M': df_monthly}, None
    except Exception as e: return None, str(e)

# ---------------------------------------------------------
# 5. 분석 로직
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
        psr = fund_data.get('PSR', 0)
        op = fund_data.get('OperatingProfit', 'N/A')
        
        if per > 0:
            if per < 15: fund_score += 5; report.append(f"- ✅ **저평가 (PER {per})**")
            elif per > 50: report.append(f"- ⚠️ **고평가 (PER {per})**")
            else: fund_score += 5; report.append(f"- ➖ **적정 (PER {per})**")
            
            if pbr < 1.2: fund_score += 5; report.append(f"- ✅ **자산주 (PBR {pbr})**")
            if psr > 0 and psr < 3.0: fund_score += 5; report.append(f"- ✅ **매출 대비 저평가 (PSR {psr})**")
            if "억원" in str(op) and not str(op).startswith("-"): report.append(f"- ✅ **영업이익 흑자**: {op}")
        else:
            report.append("- ℹ️ 재무 정보 부족")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 6. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
st.caption("한국 전 종목(펩트론 등 코스닥 포함) + ETF + 미국주식")

# 1. 데이터 로드 (내장 + ETF 전체)
all_etfs = get_all_korean_etfs() # ETF 800개 로드
static_stocks = pd.DataFrame(STATIC_STOCKS) # 대형주 로드

# 2. 검색창
search_keyword = st.text_input("종목명/ETF 입력 (예: 펩트론, 현대차, PLUS, AI)", placeholder="검색어를 입력하고 엔터를 누르세요")

selected_code = None
selected_name = None

# 3. 검색 로직 (순차적 검색)
if search_keyword:
    search_keyword = search_keyword.upper().strip()
    options = {}
    
    # [1순위] 내장 대형주에서 찾기
    res1 = static_stocks[static_stocks['Name'].str.contains(search_keyword, na=False)]
    for i, r in res1.iterrows(): options[f"{r['Name']} ({r['Code']})"] = r['Code']
    
    # [2순위] ETF 전체 리스트에서 찾기
    res2 = all_etfs[all_etfs['Name'].str.contains(search_keyword, na=False)]
    for i, r in res2.iterrows(): options[f"{r['Name']} ({r['Code']})"] = r['Code']
    
    # [3순위] 네이버 실시간 검색 (펩트론 같은 코스닥 찾기용)
    if not options:
        naver_results = search_naver_stock_code(search_keyword)
        for item in naver_results:
            options[f"{item['Name']} ({item['Code']})"] = item['Code']
            
    # [4순위] 미국 주식
    is_us = len(search_keyword) < 6 and search_keyword.isalpha()
    if is_us:
        options[f"🇺🇸 미국주식: {search_keyword}"] = search_keyword

    # 선택 박스
    if options:
        selected_option = st.selectbox("⬇️ 검색 결과 선택:", list(options.keys()))
        selected_code = options[selected_option]
        selected_name = selected_option.split('(')[0].strip()
        
        if st.button("🚀 분석하기", type="primary"): pass
    else:
        st.error("검색 결과가 없습니다.")

# 4. 분석 실행
if selected_code:
    st.divider()
    st.info(f"선택된 종목: **{selected_name}** (코드: {selected_code})")
    
    fund_data = {}
    with st.spinner("재무 데이터 수집 중..."):
        fund_data = get_fundamental_data(selected_code)

    with st.spinner("차트 데이터 분석 중..."):
        data_dict, err = get_stock_data(selected_code)
        
        if err:
            st.error(f"데이터 로딩 실패: {err}")
        else:
            raw_df = data_dict['D']
            score, report, df, ts, ps, tis, fs = analyze_advanced(data_dict, fund_data)
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
                    st.info("ETF 상품입니다. (차트 위주 분석)")
                else:
                    f1, f2 = st.columns(2)
                    f1.metric("영업이익", str(fund_data.get('OperatingProfit', '-')))
                    f1.metric("PER", fund_data.get('PER', 0))
                    f2.metric("PSR", fund_data.get('PSR', 0))
                    f2.metric("PBR", fund_data.get('PBR', 0))
                    if fund_data.get('Revenue_Trend'):
                        st.caption(f"매출 추이: {' -> '.join(fund_data['Revenue_Trend'])}")
            
            st.write("---")
            with st.expander("📝 상세 분석 내용 보기", expanded=True):
                for r in report: st.markdown(r)
            
            st.write("---")
            st.subheader("📈 시세 차트 (일봉/주봉/월봉)")
            
            tab1, tab2, tab3 = st.tabs(["일봉", "주봉", "월봉"])
            
            def draw_chart(df, title):
                df = sanitize_for_chart(df)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3], subplot_titles=(f"{title} 주가", "거래량"))
                fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'), row=1, col=1)
                if title == '일봉':
                    fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue', width=1), name='20일선'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['ma60'], line=dict(color='green', width=1), name='60일선'), row=1, col=1)
                fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='거래량'), row=2, col=1)
                fig.update_layout(height=600, xaxis_rangeslider_visible=False, showlegend=False)
                return fig

            with tab1: st.plotly_chart(draw_chart(data_dict['D'], "일봉"), use_container_width=True)
            with tab2: st.plotly_chart(draw_chart(data_dict['W'], "주봉"), use_container_width=True)
            with tab3: st.plotly_chart(draw_chart(data_dict['M'], "월봉"), use_container_width=True)
