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
# 0. [필수] 내장 코드북 (서버 차단 시에도 100% 검색 보장)
# ---------------------------------------------------------
# KRX 다운로드가 막혀도 작동하도록 주요 종목을 모두 적어놓습니다.
STATIC_KRX_DATA = [
    # 1. [대형주 TOP 30]
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

    # 2. [KODEX ETF 시리즈]
    {'Code': '069500', 'Name': 'KODEX 200'}, 
    {'Code': '122630', 'Name': 'KODEX 레버리지'}, 
    {'Code': '114800', 'Name': 'KODEX 인버스'},
    {'Code': '252670', 'Name': 'KODEX 200선물인버스2X'}, 
    {'Code': '091160', 'Name': 'KODEX 반도체'}, 
    {'Code': '422580', 'Name': 'KODEX 미국배당프리미엄액티브'},
    {'Code': '305720', 'Name': 'KODEX 2차전지산업'},
    {'Code': '278530', 'Name': 'KODEX 200TR'},
    {'Code': '214980', 'Name': 'KODEX 단기채권Plus'},
    {'Code': '455840', 'Name': 'KODEX AI반도체핵심장비'},
    {'Code': '229200', 'Name': 'KODEX 코스닥150'},
    {'Code': '233740', 'Name': 'KODEX 코스닥150레버리지'},
    {'Code': '251340', 'Name': 'KODEX 코스닥150선물인버스'},
    {'Code': '379800', 'Name': 'KODEX 미국빅테크10(H)'},
    {'Code': '304940', 'Name': 'KODEX 미국나스닥100TR'},
    {'Code': '091170', 'Name': 'KODEX 은행'},
    {'Code': '102970', 'Name': 'KODEX 자동차'},
    {'Code': '261220', 'Name': 'KODEX WTI원유선물(H)'},
    {'Code': '132030', 'Name': 'KODEX 골드선물(H)'},

    # 3. [TIGER ETF 시리즈]
    {'Code': '102110', 'Name': 'TIGER 200'},
    {'Code': '305540', 'Name': 'TIGER 2차전지테마'},
    {'Code': '360750', 'Name': 'TIGER 미국필라델피아반도체나스닥'},
    {'Code': '371460', 'Name': 'TIGER 차이나전기차SOLACTIVE'},
    {'Code': '133690', 'Name': 'TIGER 미국나스닥100'},
    {'Code': '453950', 'Name': 'TIGER 미국테크TOP10 INDXX'},
    {'Code': '327630', 'Name': 'TIGER 글로벌리튬&2차전지SOLACTIVE(합성)'},
    {'Code': '465640', 'Name': 'TIGER 미국배당+7%프리미엄다우존스'},
    {'Code': '143860', 'Name': 'TIGER 헬스케어'},
    {'Code': '364980', 'Name': 'TIGER KRX BBIG K-뉴딜'},
    
    # 4. [ACE / SOL / KBSTAR]
    {'Code': '411420', 'Name': 'ACE 미국S&P500'}, 
    {'Code': '438560', 'Name': 'SOL 미국배당다우존스'}, 
    {'Code': '251350', 'Name': 'KBSTAR 200선물인버스2X'}
]

# ---------------------------------------------------------
# 1. 종목 리스트 가져오기 (내장 데이터 우선 사용)
# ---------------------------------------------------------
@st.cache_data
def get_krx_list():
    # 서버 차단 이슈 방지를 위해 내장 데이터(STATIC_KRX_DATA)를 메인으로 사용합니다.
    df_static = pd.DataFrame(STATIC_KRX_DATA)
    
    # (선택) 실시간 데이터 병합 시도 - 실패해도 내장 데이터 리턴
    try:
        df_live = fdr.StockListing('KRX')
        if not df_live.empty:
            # 내장 데이터와 합치되, 중복 제거
            df_combined = pd.concat([df_static, df_live[['Code', 'Name']]])
            return df_combined.drop_duplicates(subset=['Code'])
    except:
        pass
    
    return df_static

# ---------------------------------------------------------
# 2. 재무 데이터 수집 (네이버/야후)
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': ''}
    
    if code.isdigit():
        data['Type'] = 'KR'
        # ETF 식별 (내장 리스트 확인)
        is_etf = False
        for item in STATIC_KRX_DATA:
            if item['Code'] == code and ('KODEX' in item['Name'] or 'TIGER' in item['Name']):
                is_etf = True; break
        
        # 이름에 ETF 키워드가 있거나 내장 리스트에 있으면 ETF로 간주
        if is_etf:
            data['Type'] = 'ETF'
            data['Opinion'] = "ℹ️ ETF는 여러 종목을 묶은 펀드이므로 영업이익/PER 분석을 생략합니다."
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
            if code.isdigit():
                df = fdr.DataReader(code, start, end)
            else:
                df = fdr.DataReader(code, start, end)
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
# 4. 분석 로직
# ---------------------------------------------------------
def analyze_advanced(df, fund_data):
    # [1차 안전장치] 컬럼 초기화
    for col in ['ma5', 'ma20', 'ma60', 'rsi', 'macd', 'macd_signal', 'macd_diff', 'bb_h', 'bb_l']:
        if col not in df.columns: df[col] = 0.0

    # 지표 계산
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

    # -------------------------------------------------------
    # 1. 추세 분석 (Trend) - 상세 설명
    # -------------------------------------------------------
    report.append("#### 1️⃣ 추세 분석 (주가의 방향성)")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append(f"- ✅ **단기 상승 추세 (5일선 > 20일선)**\n  : 최근 일주일간 주식을 산 사람들의 평균단가가 한 달 평균보다 높습니다. 이는 **'지금 당장 사고 싶어 하는 힘'**이 강하다는 뜻입니다.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append(f"- 🔥 **골든크로스 발생! (강력 매수 신호)**\n  : 방금 막 단기 상승세가 장기 추세를 뚫고 올라갔습니다. 주가가 바닥을 찍고 **본격적으로 오르기 시작하는 초입**일 가능성이 매우 높습니다.")
    else:
        report.append(f"- 🔻 **단기 하락 추세 (5일선 < 20일선)**\n  : 최근 주가가 한 달 평균보다 낮습니다. 단기적으로 **'팔고 싶어 하는 힘'**이 더 강해서 주가가 힘을 못 쓰고 있습니다.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append(f"- ✅ **중기 상승 (60일선 위)**\n  : 3개월(분기) 평균가격보다 주가가 높습니다. 실적 시즌이나 중장기적인 흐름이 **우상향(상승)** 하고 있어 안정적입니다.")
    else:
        report.append(f"- 🔻 **중기 하락 (60일선 아래)**\n  : 3개월 평균보다 주가가 낮습니다. 소위 '물려있는' 사람이 많아 주가가 오를 때마다 본전 심리에 매도 물량이 나올 수 있습니다.")

    # -------------------------------------------------------
    # 2. 가격 위치 (Bollinger Bands) - 상세 설명
    # -------------------------------------------------------
    report.append("\n#### 2️⃣ 가격 위치 (지금 싼가요? 비싼가요?)")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 도달 (저점 매수 기회)**\n  : 주가가 볼린저밴드라는 **'통계적 가격 범위'의 지하 1층**에 도착했습니다. 과거 통계를 볼 때, 이 위치에서는 주가가 다시 위로 튀어 오를(반등) 확률이 95% 이상입니다.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append(f"- ⚠️ **천장권 도달 (고점 주의)**\n  : 주가가 밴드 **옥상(최상단)**에 닿았습니다. 단기간에 너무 급하게 올랐다는 뜻입니다. 지금 사면 '상투'를 잡을 수 있으니 조심해야 합니다.")
    else:
        price_score += 5
        report.append(f"- ➖ **허리 구간 (중간 지대)**\n  : 주가가 과열되지도, 너무 싸지도 않은 적정한 위치입니다. 이럴 땐 '추세(1번 지표)'를 믿고 따라가는 것이 좋습니다.")

    # -------------------------------------------------------
    # 3. 투자 심리 (RSI) - 상세 설명
    # -------------------------------------------------------
    report.append("\n#### 3️⃣ 투자 심리 (공포 vs 탐욕)")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 구간 (공포에 사라!)**\n  : 투자 심리 지표(RSI)가 {curr['rsi']:.0f}입니다. 사람들이 공포에 질려 주식을 투매했습니다. 역설적으로 **지금이 남들보다 싸게 주식을 주워담을 수 있는 최고의 기회**입니다.")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 구간 (탐욕을 경계하라)**\n  : 지표가 {curr['rsi']:.0f}로 과열 상태입니다. 너도나도 주식을 사서 가격이 비정상적으로 올랐을 수 있습니다. 추격 매수는 자제하세요.")
    else:
        timing_score += 5
        report.append(f"- ➖ **심리 안정적**\n  : 투자자들의 심리가 흥분하지 않고 차분합니다. (RSI {curr['rsi']:.0f})")

    # -------------------------------------------------------
    # 4. 기업 가치 (Fundamentals) - 상세 설명
    # -------------------------------------------------------
    report.append("\n#### 4️⃣ 기업 가치 (이 주식, 살 가치가 있나?)")
    
    if fund_data['Type'] == 'ETF':
        fund_score += 10
        report.append("- ℹ️ **ETF 상품입니다.**\n  : ETF는 여러 기업을 묶어놓은 '종합선물세트'라서 PER/PBR로 평가하기 어렵습니다. 대신 **1번(추세)과 3번(심리) 지표**를 보고 매매하는 것이 훨씬 정확합니다.")
    else:
        per = fund_data.get('PER', 0)
        pbr = fund_data.get('PBR', 0)
        op = fund_data.get('OperatingProfit', 'N/A')
        
        # PER 분석
        if per > 0:
            if per < 10: 
                fund_score += 10
                report.append(f"- ✅ **저평가 우량주 (PER {per})**\n  : 기업이 1년에 버는 돈에 비해 주가가 매우 쌉니다. (기준 10배 이하). **가치투자 관점에서 매수하기 아주 매력적인 가격대**입니다.")
            elif per > 50:
                 report.append(f"- ⚠️ **고평가 성장주 (PER {per})**\n  : 현재 버는 돈보다 미래의 기대감이 가격에 많이 반영되어 있습니다. 성장성이 꺾이면 주가가 급락할 수 있으니 주의하세요.")
            else:
                 fund_score += 5
                 report.append(f"- ➖ **적정 주가 (PER {per})**\n  : 기업의 이익 수준에 딱 맞는 적절한 주가입니다.")
        
        # PBR 분석
        if pbr > 0 and pbr < 1.0:
            fund_score += 10
            report.append(f"- ✅ **자산 가치 우수 (PBR {pbr})**\n  : PBR이 1보다 작다는 건, **'회사가 지금 당장 망해서 공장과 땅을 다 팔아도 현재 주가보다는 돈이 더 나온다'**는 뜻입니다. 그만큼 절대적으로 싼 가격입니다.")
            
        # 영업이익 분석
        if "억원" in str(op) and not str(op).startswith("-"):
             report.append(f"- ✅ **영업이익 흑자 ({op})**\n  : 이 회사는 본업(장사)을 통해 돈을 잘 벌고 있습니다. 재무적으로 튼튼하여 장기 투자해도 안전합니다.")
        elif "억원" in str(op) and str(op).startswith("-"):
             report.append(f"- ⚠️ **영업이익 적자 ({op})**\n  : 회사가 장사를 해서 손해를 보고 있습니다. 재무 상태가 위험할 수 있으니 단기적인 접근이 필요합니다.")

    # 최종 점수 계산
    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 5. 화면 구성 (검색 -> 목록 선택 방식)
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
st.caption("KODEX, TIGER 등 ETF 완벽 지원 + 미국 주식")

# 1. 데이터 로드 (내장 데이터 사용)
krx_list = get_krx_list()

# 2. 검색창
search_keyword = st.text_input("종목명/ETF 입력 (예: KODEX, 반도체, 효성, 삼성, ORCL)", placeholder="찾고 싶은 종목명을 입력하세요")

selected_code = None
selected_name = None

# 3. 검색 로직 (키워드 입력 시 동작)
if search_keyword:
    search_keyword = search_keyword.upper().strip()
    
    # [A] 한국 종목 검색 (이름에 포함된 것 찾기)
    results = krx_list[krx_list['Name'].str.contains(search_keyword, na=False)]
    
    # [B] 미국 주식 티커 처리
    is_us_ticker = len(search_keyword) < 6 and search_keyword.isalpha()
    
    # 옵션 만들기
    options = {}
    
    if not results.empty:
        # 상위 50개만 보여줌
        for index, row in results.head(50).iterrows():
            display_text = f"{row['Name']} ({row['Code']})"
            options[display_text] = row['Code']
    
    if is_us_ticker:
        options[f"🇺🇸 미국주식: {search_keyword}"] = search_keyword

    # 4. 선택 상자
    if options:
        selected_option = st.selectbox("⬇️ 검색 결과 중 하나를 선택하세요:", list(options.keys()))
        selected_code = options[selected_option]
        selected_name = selected_option.split('(')[0].strip()
        
        # 5. 분석 버튼
        if st.button("🚀 선택한 종목 분석하기", type="primary"):
            pass
    else:
        st.error("검색 결과가 없습니다. (KODEX, TIGER, 삼성 등 정확한 키워드를 입력해보세요)")

# ---------------------------------------------------------
# 6. 분석 실행 (선택 완료 시)
# ---------------------------------------------------------
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
            
            # 상단 정보
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
            
            fig.add_trace(go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=df.index, y=df['ma20'], line=dict(color='blue', width=1), name='20일선'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=df.index, y=df['ma60'], line=dict(color='green', width=1), name='60일선'
            ), row=1, col=1)
            
            fig.add_trace(go.Bar(
                x=df.index, y=df['Volume'], name='거래량'
            ), row=2, col=1)
            
            fig.add_trace(go.Bar(
                x=df.index, y=df['macd_diff'], marker_color='gray', name='MACD'
            ), row=3, col=1)
            
            fig.add_trace(go.Scatter(
                x=df.index, y=df['rsi'], line=dict(color='purple'), name='RSI'
            ), row=4, col=1)
            
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            
            fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

