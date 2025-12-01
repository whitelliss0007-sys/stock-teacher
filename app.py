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
# 1. [핵심] 네이버 검색창 빌려쓰기 (만능 검색 기능)
# ---------------------------------------------------------
def search_naver_stocks(keyword):
    """
    네이버 증권의 자동완성 검색 기능을 빌려와서
    사용자가 입력한 키워드에 맞는 종목 코드와 이름을 가져옵니다.
    """
    try:
        # 네이버 증권 자동완성 API URL
        url = f"https://ac.finance.naver.com/ac?q={keyword}&q_enc=euc-kr&st=111&r_format=json&r_enc=euc-kr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        data = response.json()
        
        search_results = []
        
        # 네이버 응답 데이터 파싱 (items 리스트 추출)
        if 'items' in data and len(data['items']) > 0:
            for item in data['items'][0]:
                # item 구조: [종목명, 종목코드, ...]
                name = item[0]
                code = item[1]
                # 코스피/코스닥/ETF 구분 없이 다 가져옴
                search_results.append({'Name': name, 'Code': code})
                
        return pd.DataFrame(search_results)
    except:
        return pd.DataFrame()

# ---------------------------------------------------------
# 2. 재무 데이터 수집 (네이버/야후)
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
            
            # ETF 여부 확인 (제목이나 태그로 판단)
            stock_name = ""
            try: stock_name = soup.select_one('.wrap_company h2 a').text
            except: pass
            
            # 이름에 ETF 관련 키워드가 있으면 ETF로 분류
            etf_keywords = ['ETF', 'ETN', 'KODEX', 'TIGER', 'KBSTAR', 'ACE', 'SOL', 'HANARO', 'KOSEF', 'ARIRANG']
            if any(k in stock_name.upper() for k in etf_keywords):
                data['Type'] = 'ETF'
                data['Opinion'] = "ℹ️ ETF 상품입니다. (구성 종목과 추세가 중요)"
            
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

            # 기업인 경우만 상세 재무 (영업이익 등) 크롤링
            if data['Type'] != 'ETF':
                try:
                    dfs = pd.read_html(response.text, match='매출액')
                    if dfs:
                        fin_df = dfs[-1]
                        target_col = -2 # 최근 결산
                        
                        op_row = fin_df[fin_df.iloc[:, 0].str.contains('영업이익', na=False)]
                        if not op_row.empty: 
                            val = op_row.iloc[0, target_col]
                            data['OperatingProfit'] = f"{val} 억원"
                        
                        roe_row = fin_df[fin_df.iloc[:, 0].str.contains('ROE', na=False)]
                        if not roe_row.empty: 
                            val = roe_row.iloc[0, target_col]
                            data['ROE'] = f"{val} %"
                            
                        # 매출액 추이 & PSR
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

    else: # 미국 주식
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
# 3. 차트 데이터 (안전장치)
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*3)
        
        try:
            if code.isdigit():
                df = fdr.DataReader(code, start, end)
                if df.empty: df = fdr.DataReader(f"{code}.KS", start, end)
                if df.empty: df = fdr.DataReader(f"{code}.KQ", start, end)
            else:
                df = fdr.DataReader(code, start, end)
        except: df = pd.DataFrame()

        # 야후 비상 회로
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
# 4. 분석 로직 (치킨집 비유 + 상세 설명)
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
    report.append("#### 1️⃣ 추세 분석 (방향)")
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
    report.append("\n#### 2️⃣ 가격 위치 (고점/저점)")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append("- ✅ **바닥권 도달 (+15점)**: 반등 기대.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append("- ⚠️ **천장권 도달 (0점)**: 조정 주의.")
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

    # 4. 가치 (치킨집 비유)
    report.append("\n#### 4️⃣ 기업 가치 (펀더멘털)")
    if fund_data['Type'] == 'ETF' or fund_data['Type'] == 'US':
        fund_score += 10
        report.append("- ℹ️ **ETF/해외주식**: 차트와 추세 위주로 분석합니다.")
    else:
        per = fund_data.get('PER', 0)
        pbr = fund_data.get('PBR', 0)
        psr = fund_data.get('PSR', 0)
        op = fund_data.get('OperatingProfit', 'N/A')
        
        if per > 0:
            if per < 15: 
                fund_score += 5; report.append(f"- ✅ **저평가 (PER {per})**: 치킨집 본전 뽑는데 {per}년.")
            elif per > 50:
                 report.append(f"- ⚠️ **고평가 (PER {per})**: 미래 기대감 반영됨.")
            else:
                 fund_score += 5; report.append(f"- ➖ **적정 (PER {per})**: 적절한 가격.")
            
            if pbr < 1.2:
                fund_score += 5; report.append(f"- ✅ **자산주 (PBR {pbr})**: 망해도 짐만 팔아도 본전.")
                
            if psr > 0 and psr < 3.0:
                fund_score += 5; report.append(f"- ✅ **매출 대비 저평가 (PSR {psr})**")

            if "억원" in str(op) and not str(op).startswith("-"):
                 report.append(f"- ✅ **영업이익 흑자**: 돈 잘 버는 맛집입니다.")
        else:
            report.append("- ℹ️ 재무 정보 부족")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 5. 화면 구성 (네이버 검색 기능 탑재)
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
st.caption("네이버 실시간 검색 연동 (모든 ETF/중소형주/미국주식 검색 가능)")

search_keyword = st.text_input("종목명/ETF 입력 (예: 중소형, 반도체, 펩트론, KODEX, 테슬라)", placeholder="검색어를 입력하고 엔터를 누르세요")

selected_code = None
selected_name = None

if search_keyword:
    search_keyword = search_keyword.strip()
    
    # 1. 네이버 증권 검색 (여기가 핵심!)
    # 어떤 키워드(중소형, 펩트론 등)를 넣어도 네이버가 찾아줌
    naver_results = search_naver_stocks(search_keyword)
    
    options = {}
    if not naver_results.empty:
        # 네이버 검색 결과 표시
        for i, row in naver_results.iterrows():
            # row['Code']가 6자리면 한국주식, 아니면 기타
            # 여기서는 편의상 다 보여줌
            options[f"{row['Name']} ({row['Code']})"] = row['Code']
    
    # 미국 주식(티커) 직접 입력 옵션 추가
    if len(search_keyword) < 6 and search_keyword.isalpha():
        options[f"🇺🇸 미국주식: {search_keyword.upper()}"] = search_keyword.upper()

    if options:
        selected_option = st.selectbox("⬇️ 검색 결과 중 하나를 선택하세요:", list(options.keys()))
        selected_code = options[selected_option]
        selected_name = selected_option.split('(')[0].strip()
        
        if st.button("🚀 선택한 종목 분석하기", type="primary"):
            pass
    else:
        st.warning("검색 결과가 없습니다.")

# 6. 분석 실행
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
                    st.info(f"{fund_data.get('Opinion', 'ETF 상품입니다.')}")
                else:
                    f1, f2 = st.columns(2)
                    f1.metric("영업이익", str(fund_data.get('OperatingProfit', '-')))
                    f1.metric("PER", fund_data.get('PER', 0))
                    f2.metric("PSR", fund_data.get('PSR', 0))
                    f2.metric("PBR", fund_data.get('PBR', 0))
                    if fund_data.get('Revenue_Trend'):
                        st.caption(f"매출 추이: {' -> '.join(fund_data['Revenue_Trend'])}")
            
            st.write("---")
            with st.expander("📝 상세 분석 내용 보기 (클릭)", expanded=True):
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
