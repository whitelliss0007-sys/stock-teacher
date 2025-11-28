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
# 0. [필수] 내장 코드북 (서버 차단 시 비상용 명부)
# ---------------------------------------------------------
STATIC_KRX_DATA = [
    # [대형주]
    {'Code': '005930', 'Name': '삼성전자'}, {'Code': '000660', 'Name': 'SK하이닉스'},
    {'Code': '373220', 'Name': 'LG에너지솔루션'}, {'Code': '207940', 'Name': '삼성바이오로직스'},
    {'Code': '005380', 'Name': '현대차'}, {'Code': '000270', 'Name': '기아'},
    {'Code': '068270', 'Name': '셀트리온'}, {'Code': '005490', 'Name': 'POSCO홀딩스'},
    {'Code': '035420', 'Name': 'NAVER'}, {'Code': '035720', 'Name': '카카오'},
    {'Code': '006400', 'Name': '삼성SDI'}, {'Code': '051910', 'Name': 'LG화학'},
    {'Code': '086520', 'Name': '에코프로'}, {'Code': '247540', 'Name': '에코프로비엠'},
    {'Code': '298020', 'Name': '효성중공업'}, {'Code': '004800', 'Name': '효성'},
    {'Code': '042700', 'Name': '한미반도체'}, {'Code': '012450', 'Name': '한화에어로스페이스'},
    # [KODEX ETF]
    {'Code': '069500', 'Name': 'KODEX 200'}, {'Code': '122630', 'Name': 'KODEX 레버리지'},
    {'Code': '252670', 'Name': 'KODEX 200선물인버스2X'}, {'Code': '114800', 'Name': 'KODEX 인버스'},
    {'Code': '091160', 'Name': 'KODEX 반도체'}, {'Code': '422580', 'Name': 'KODEX 미국배당프리미엄액티브'},
    {'Code': '278530', 'Name': 'KODEX 미국S&P500TR'}, {'Code': '304940', 'Name': 'KODEX 미국나스닥100TR'},
    {'Code': '455840', 'Name': 'KODEX AI반도체핵심장비'}, {'Code': '214980', 'Name': 'KODEX 단기채권Plus'},
    # [TIGER ETF]
    {'Code': '360750', 'Name': 'TIGER 미국필라델피아반도체나스닥'}, {'Code': '371460', 'Name': 'TIGER 차이나전기차SOLACTIVE'},
    {'Code': '305540', 'Name': 'TIGER 2차전지테마'}, {'Code': '133690', 'Name': 'TIGER 미국나스닥100'},
    {'Code': '102110', 'Name': 'TIGER 200'}, {'Code': '453950', 'Name': 'TIGER 미국테크TOP10 INDXX'},
    # [기타 ETF]
    {'Code': '411420', 'Name': 'ACE 미국S&P500'}, {'Code': '438560', 'Name': 'SOL 미국배당다우존스'}
]

# ---------------------------------------------------------
# 1. 종목 리스트 가져오기
# ---------------------------------------------------------
@st.cache_data
def get_krx_list():
    try:
        df = fdr.StockListing('KRX')
        if not df.empty: return df[['Code', 'Name']]
    except: pass
    return pd.DataFrame(STATIC_KRX_DATA)

# ---------------------------------------------------------
# 2. 재무 데이터 수집
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': ''}
    
    if code.isdigit():
        data['Type'] = 'KR'
        # ETF 식별
        is_etf = False
        for item in STATIC_KRX_DATA:
            if item['Code'] == code and ('ETF' in item['Name'] or 'KODEX' in item['Name'] or 'TIGER' in item['Name']):
                is_etf = True; break
        
        if is_etf:
            data['Type'] = 'ETF'
            data['Opinion'] = "ℹ️ ETF는 여러 기업을 묶은 펀드이므로 영업이익/PER 분석을 생략합니다."
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

    else: # 미국 주식
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
# 3. 차트 데이터 (안전장치)
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2)
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
# 4. 상세 분석 로직 (설명 강화)
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

    # (1) 추세
    report.append("#### 1️⃣ 추세 분석 (주가의 방향)")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append(f"- ✅ **단기 상승 (+15점)**\n  : 5일 평균가격이 20일 평균보다 높습니다. 최근 매수세가 강해졌다는 신호입니다.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append(f"- 🔥 **골든크로스 (+10점)**\n  : 방금 막 상승 추세로 전환되었습니다. 매수하기 좋은 타이밍입니다.")
    else:
        report.append(f"- 🔻 **단기 하락 (0점)**\n  : 5일선이 20일선 아래에 있습니다. 파는 힘이 더 강합니다.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append(f"- ✅ **중기 상승 (+5점)**\n  : 60일선(수급선) 위에 있습니다. 3개월 추세가 살아있습니다.")

    # (2) 가격
    report.append("\n#### 2️⃣ 가격 위치 (저점/고점)")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 도달 (+15점)**\n  : 주가가 밴드 최하단에 있습니다. 반등할 확률이 높습니다.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append(f"- ⚠️ **천장권 도달 (0점)**\n  : 주가가 너무 급하게 올랐습니다. 조정받을 수 있으니 조심하세요.")
    else:
        price_score += 5
        report.append(f"- ➖ **중간 지대 (+5점)**\n  : 과열되지도 침체되지도 않은 허리 구간입니다.")

    # (3) 심리
    report.append("\n#### 3️⃣ 투자 심리")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 구간 (+20점)**\n  : 공포에 질려 너무 많이 팔았습니다. 저점 매수 기회입니다!")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 구간 (0점)**\n  : 너무 많이 샀습니다. 탐욕 구간이니 추격 매수는 위험합니다.")
    else:
        timing_score += 5
        report.append(f"- ➖ **심리 안정 (+5점)**\n  : 투자 심리가 안정적입니다.")

    # (4) 가치
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
                report.append(f"- ✅ **저평가 (PER {per}) (+10점)**\n  : 기업이 버는 돈에 비해 주가가 쌉니다.")
            elif per > 50:
                 report.append(f"- ⚠️ **고평가 (PER {per}) (0점)**\n  : 미래 기대감이 많이 반영되어 비쌉니다.")
            else:
                 fund_score += 5
                 report.append(f"- ➖ **적정 주가 (PER {per}) (+5점)**\n  : 적정한 가격대입니다.")
            
            if "억원" in str(op) and not str(op).startswith("-"):
                 report.append(f"- ✅ **영업이익 흑자 ({op})**\n  : 돈을 잘 벌고 있는 튼튼한 회사입니다.")
        else:
            report.append("- ℹ️ 재무 정보 부족")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 5. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
st.caption("ETF 대폭 추가 + 상세 설명 + 검색 오류 해결")

krx_list = get_krx_list()

# 검색창
search_keyword = st.text_input("종목명/ETF 입력 (예: 반도체, KODEX, 효성, 삼성)", placeholder="검색어를 입력하고 엔터를 누르세요")

selected_code = None
selected_name = None

if search_keyword:
    search_keyword = search_keyword.upper().strip()
    results = krx_list[krx_list['Name'].str.contains(search_keyword, na=False)]
    is_us_ticker = len(search_keyword) < 6 and search_keyword.isalpha()
    
    options = {}
    if not results.empty:
        for index, row in results.head(50).iterrows():
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

# 분석 실행
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
                if "ETF" in str(fund_data['Type']):
                    st.info("ETF 상품입니다. (영업이익 분석 제외)")
                else:
                    f1, f2 = st.columns(2)
                    f1.metric("영업이익", str(fund_data.get('OperatingProfit', '-')))
                    f1.metric("PER", fund_data.get('PER', 0))
                    f2.metric("ROE", fund_data.get('ROE', '-'))
                    f2.metric("PBR", fund_data.get('PBR', 0))
            
            st.write("---")
            with st.expander("📝 선생님의 상세 분석 이유 (클릭해서 보세요)", expanded=True):
                for r in report: st.markdown(r)
            
            st.write("---")
            st.subheader("📈 4단 정밀 차트")
            
            df = sanitize_for_chart(df)
            
            # 차트 (줄바꿈 오류 방지용 한 줄 작성)
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
