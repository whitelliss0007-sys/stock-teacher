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
import time

st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")

# ---------------------------------------------------------
# 0. [필수] 내장 코드북 (서버 차단 시 비상용 명부)
# ---------------------------------------------------------
STATIC_KRX_DATA = [
    # [대형주 TOP 50 & 우량주]
    {'Code': '005930', 'Name': '삼성전자'}, {'Code': '000660', 'Name': 'SK하이닉스'},
    {'Code': '373220', 'Name': 'LG에너지솔루션'}, {'Code': '207940', 'Name': '삼성바이오로직스'},
    {'Code': '005380', 'Name': '현대차'}, {'Code': '000270', 'Name': '기아'},
    {'Code': '068270', 'Name': '셀트리온'}, {'Code': '005490', 'Name': 'POSCO홀딩스'},
    {'Code': '035420', 'Name': 'NAVER'}, {'Code': '035720', 'Name': '카카오'},
    {'Code': '006400', 'Name': '삼성SDI'}, {'Code': '051910', 'Name': 'LG화학'},
    {'Code': '086520', 'Name': '에코프로'}, {'Code': '247540', 'Name': '에코프로비엠'},
    {'Code': '000810', 'Name': '삼성화재'}, {'Code': '032830', 'Name': '삼성생명'},
    {'Code': '055550', 'Name': '신한지주'}, {'Code': '105560', 'Name': 'KB금융'},
    {'Code': '028260', 'Name': '삼성물산'}, {'Code': '012330', 'Name': '현대모비스'},
    {'Code': '015760', 'Name': '한국전력'}, {'Code': '034020', 'Name': '두산에너빌리티'},
    {'Code': '012450', 'Name': '한화에어로스페이스'}, {'Code': '042700', 'Name': '한미반도체'},
    {'Code': '298020', 'Name': '효성중공업'}, {'Code': '004800', 'Name': '효성'},
    {'Code': '298050', 'Name': '효성첨단소재'}, {'Code': '298000', 'Name': '효성티앤씨'},
    {'Code': '010120', 'Name': 'LS일렉트릭'}, {'Code': '003550', 'Name': 'LG'},
    {'Code': '034730', 'Name': 'SK'}, {'Code': '017670', 'Name': 'SK텔레콤'},
    {'Code': '011200', 'Name': 'HMM'}, {'Code': '010950', 'Name': 'S-Oil'},
    {'Code': '009150', 'Name': '삼성전기'}, {'Code': '032640', 'Name': 'LG유플러스'},
    {'Code': '003490', 'Name': '대한항공'}, {'Code': '086790', 'Name': '하나금융지주'},
    
    # [KODEX ETF]
    {'Code': '069500', 'Name': 'KODEX 200'}, {'Code': '122630', 'Name': 'KODEX 레버리지'}, 
    {'Code': '114800', 'Name': 'KODEX 인버스'}, {'Code': '252670', 'Name': 'KODEX 200선물인버스2X'}, 
    {'Code': '091160', 'Name': 'KODEX 반도체'}, {'Code': '422580', 'Name': 'KODEX 미국배당프리미엄액티브'},
    {'Code': '305720', 'Name': 'KODEX 2차전지산업'}, {'Code': '278530', 'Name': 'KODEX 200TR'},
    {'Code': '214980', 'Name': 'KODEX 단기채권Plus'}, {'Code': '455840', 'Name': 'KODEX AI반도체핵심장비'},
    {'Code': '229200', 'Name': 'KODEX 코스닥150'}, {'Code': '233740', 'Name': 'KODEX 코스닥150레버리지'},
    {'Code': '251340', 'Name': 'KODEX 코스닥150선물인버스'}, {'Code': '379800', 'Name': 'KODEX 미국빅테크10(H)'},
    {'Code': '304940', 'Name': 'KODEX 미국나스닥100TR'}, {'Code': '091170', 'Name': 'KODEX 은행'},
    {'Code': '102970', 'Name': 'KODEX 자동차'}, {'Code': '261220', 'Name': 'KODEX WTI원유선물(H)'},
    {'Code': '132030', 'Name': 'KODEX 골드선물(H)'}, {'Code': '449190', 'Name': 'KODEX K-로봇액티브'},

    # [TIGER ETF]
    {'Code': '102110', 'Name': 'TIGER 200'}, {'Code': '305540', 'Name': 'TIGER 2차전지테마'},
    {'Code': '360750', 'Name': 'TIGER 미국필라델피아반도체나스닥'}, {'Code': '371460', 'Name': 'TIGER 차이나전기차SOLACTIVE'},
    {'Code': '133690', 'Name': 'TIGER 미국나스닥100'}, {'Code': '453950', 'Name': 'TIGER 미국테크TOP10 INDXX'},
    {'Code': '327630', 'Name': 'TIGER 글로벌리튬&2차전지SOLACTIVE(합성)'}, {'Code': '465640', 'Name': 'TIGER 미국배당+7%프리미엄다우존스'},
    {'Code': '143860', 'Name': 'TIGER 헬스케어'}, {'Code': '364980', 'Name': 'TIGER KRX BBIG K-뉴딜'},
    
    # [ACE / SOL / KBSTAR]
    {'Code': '411420', 'Name': 'ACE 미국S&P500'}, {'Code': '438560', 'Name': 'SOL 미국배당다우존스'}, 
    {'Code': '251350', 'Name': 'KBSTAR 200선물인버스2X'}
]

# ---------------------------------------------------------
# 1. 종목 리스트 가져오기
# ---------------------------------------------------------
@st.cache_data
def get_krx_list():
    try:
        df_static = pd.DataFrame(STATIC_KRX_DATA)
        df_live = fdr.StockListing('KRX')
        if not df_live.empty:
            df_live = df_live[['Code', 'Name']]
            df_combined = pd.concat([df_static, df_live], ignore_index=True)
            return df_combined.drop_duplicates(subset=['Code'], keep='last')
    except: pass
    return pd.DataFrame(STATIC_KRX_DATA)

# ---------------------------------------------------------
# 2. 재무 데이터 수집 (네이버/야후)
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': '', 'Revenue_Trend': [], 'PSR': 0}
    
    if code.isdigit():
        data['Type'] = 'KR'
        # ETF 식별
        is_etf = False
        for item in STATIC_KRX_DATA:
            if item['Code'] == code and ('ETF' in item['Name'] or 'KODEX' in item['Name'] or 'TIGER' in item['Name'] or 'ACE' in item['Name']):
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
# 3. 차트 데이터 (안전장치 강화)
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
# 4. 분석 로직 (복사 오류 방지용 안전 코드)
# ---------------------------------------------------------
def analyze_advanced(data_dict, fund_data):
    df = data_dict['D'].copy()
    
    # [안전장치] 컬럼 리스트를 분리해서 작성 (오류 방지)
    check_cols = [
        'ma5', 'ma20', 'ma60', 'rsi', 
        'macd', 'macd_signal', 'macd_diff', 
        'bb_h', 'bb_l'
    ]
    for col in check_cols:
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
    report.append("#### 1️⃣ 추세 분석 (Trend)")
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

    # 2. 가격
    report.append("\n#### 2️⃣ 가격 위치 (Price Action)")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 도달 (+15점)**\n  : 주가가 밴드 최하단에 있습니다. 반등할 확률이 높습니다.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append(f"- ⚠️ **천장권 도달 (0점)**\n  : 주가가 너무 급하게 올랐습니다. 조정받을 수 있으니 조심하세요.")
    else:
        price_score += 5
        report.append(f"- ➖ **중간 지대 (+5점)**\n  : 과열되지도 침체되지도 않은 허리 구간입니다.")

    # 3. 심리
    report.append("\n#### 3️⃣ 투자 심리")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 구간 (+20점)**\n  : 공포에 질려 너무 많이 팔았습니다. 저점 매수 기회입니다!")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 구간 (0점)**\n  : 너무 많이 샀습니다. 탐욕 구간이니 추격 매수는 위험합니다.")
    else:
        timing_score += 5
        report.append(f"- ➖ **심리 안정 (+5점)**\n  : 투자 심리가 안정적입니다.")

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
            if per < 15: 
                fund_score += 5; report.append(f"- ✅ **저평가 (PER {per})**\n  : 이익 대비 주가가 쌉니다.")
            elif per > 50:
                 report.append(f"- ⚠️ **고평가 (PER {per})**\n  : 미래 기대감이 많이 반영되어 있습니다.")
            else:
                 fund_score += 5; report.append(f"- ➖ **적정 (PER {per})**\n  : 적당한 가격입니다.")
            
            if pbr < 1.2:
                fund_score += 5; report.append(f"- ✅ **자산주 (PBR {pbr})**\n  : 망해도 본전은 건지는 가격대입니다.")
                
            if psr > 0 and psr < 3.0:
                fund_score += 5; report.append(f"- ✅ **매출 대비 저평가 (PSR {psr})**\n  : 시가총액이 매출액과 비슷하거나 작습니다.")

            if "억원" in str(op) and not str(op).startswith("-"):
                 report.append(f"- ✅ **영업이익 흑자 ({op})**\n  : 돈을 잘 벌고 있는 튼튼한 회사입니다.")
        else:
            report.append("- ℹ️ 재무 정보 부족")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

def sanitize_for_chart(df):
    check_cols = ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']
    for col in check_cols:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 5. [신규] 우량주 발굴 로직 (치킨집 비유 적용)
# ---------------------------------------------------------
def scan_undervalued_stocks():
    gems = []
    # ETF 제외하고 일반 기업만 스캔
    target_stocks = [s for s in STATIC_KRX_DATA if 'KODEX' not in s['Name'] and 'TIGER' not in s['Name'] and 'ACE' not in s['Name']]
    
    progress_text = "보물을 찾는 중입니다... 잠시만 기다려주세요."
    my_bar = st.progress(0, text=progress_text)
    
    for i, stock in enumerate(target_stocks):
        my_bar.progress((i + 1) / len(target_stocks), text=f"🔍 분석 중: {stock['Name']}")
        try:
            f_data = get_fundamental_data(stock['Code'])
            per = f_data.get('PER', 0)
            pbr = f_data.get('PBR', 0)
            psr = f_data.get('PSR', 0)
            roe_str = str(f_data.get('ROE', '0')).replace('%', '').strip()
            roe = float(roe_str) if roe_str.replace('.', '', 1).isdigit() else 0
            
            reasons = []
            
            # [조건 1] PER 15 이하 -> "본전 뽑는데 걸리는 시간"
            if 0 < per <= 15:
                reasons.append(f"💰 **싸다! (PER {per})**: 치킨집 본전 뽑는데 {per}년밖에 안 걸려요. (저평가)")
                
            # [조건 2] PBR 1.2 이하 -> "망해도 건질 게 있다"
            if 0 < pbr <= 1.2:
                reasons.append(f"🏗️ **땡처리 이득! (PBR {pbr})**: 가게 문 닫고 짐만 팔아도 본전은 건집니다. (자산가치 우수)")
            
            # [조건 3] ROE 10 이상 -> "장사 실력 점수"
            if roe >= 10:
                reasons.append(f"👨‍🍳 **장사의 신! (ROE {roe}%)**: 사장님이 돈 굴리는 실력이 아주 좋습니다.")
                
            # [조건 4] 영업이익 흑자 -> "진짜 요리 실력"
            op = f_data.get('OperatingProfit', 'N/A')
            if "억원" not in str(op) or str(op).startswith("-"):
                continue # 적자는 무조건 탈락
            
            # 추천 기준: 좋은 이유가 2개 이상이면 합격
            if len(reasons) >= 2:
                gems.append({'Name': stock['Name'], 'Code': stock['Code'], 'Reasons': reasons, 'Data': f_data})
                
        except: continue
        
    my_bar.empty()
    return gems

# ---------------------------------------------------------
# 6. 화면 구성 (탭 기능: 검색 vs 추천)
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")

tab_search, tab_recommend = st.tabs(["🔍 종목 분석 (검색)", "💎 우량주 발굴 (AI 추천)"])

# === [탭 1] 기존 검색 기능 ===
with tab_search:
    st.caption("한국/미국 주식 + ETF + PSR/매출 분석")
    krx_list = get_krx_list()
    search_keyword = st.text_input("종목명/ETF 입력", placeholder="삼성전자, KODEX, 테슬라 등...")
    
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
            selected_option = st.selectbox("⬇️ 검색 결과 선택:", list(options.keys()))
            selected_code = options[selected_option]
            selected_name = selected_option.split('(')[0].strip()
            if st.button("🚀 분석하기", type="primary"): pass
        else:
            st.error("검색 결과가 없습니다.")

    if selected_code:
        st.divider()
        fund_data = {}
        with st.spinner("데이터 분석 중..."):
            fund_data = get_fundamental_data(selected_code)
            data_dict, err = get_stock_data(selected_code)
            
            if err:
                st.error("데이터 부족")
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
                    f1, f2 = st.columns(2)
                    f1.metric("영업이익", str(fund_data.get('OperatingProfit', '-')))
                    f1.metric("PER", fund_data.get('PER', 0))
                    f2.metric("PSR", fund_data.get('PSR', 0))
                    f2.metric("PBR", fund_data.get('PBR', 0))
                    if fund_data.get('Revenue_Trend'):
                        st.caption(f"매출: {' -> '.join(fund_data['Revenue_Trend'])}")
                
                with st.expander("📝 상세 분석 내용", expanded=True):
                    for r in report: st.markdown(r)
                
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

# === [탭 2] 우량주 발굴 기능 ===
with tab_recommend:
    st.header("💎 숨겨진 보석(우량주) 찾기")
    st.write("AI가 주요 종목을 샅샅이 뒤져서 **싸고, 돈 잘 벌고, 튼튼한** 기업을 찾아냅니다.")
    
    if st.button("🚀 보물 찾기 시작! (약 10초 소요)", type="primary"):
        gems = scan_undervalued_stocks()
        if gems:
            st.success(f"총 {len(gems)}개의 보물을 발견했습니다!")
            for gem in gems:
                with st.container():
                    st.subheader(f"🎁 {gem['Name']} ({gem['Code']})")
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        for reason in gem['Reasons']: st.info(reason)
                    with c2:
                        st.metric("PER", gem['Data'].get('PER'))
                        st.metric("PBR", gem['Data'].get('PBR'))
                    st.divider()
        else:
            st.warning("아쉽게도 완벽한 조건에 맞는 보물을 찾지 못했습니다.")
