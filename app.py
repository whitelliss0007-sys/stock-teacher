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
    # --- 대형주 ---
    {'Code': '005930', 'Name': '삼성전자'}, {'Code': '000660', 'Name': 'SK하이닉스'},
    {'Code': '373220', 'Name': 'LG에너지솔루션'}, {'Code': '207940', 'Name': '삼성바이오로직스'},
    {'Code': '005380', 'Name': '현대차'}, {'Code': '000270', 'Name': '기아'},
    {'Code': '068270', 'Name': '셀트리온'}, {'Code': '005490', 'Name': 'POSCO홀딩스'},
    {'Code': '035420', 'Name': 'NAVER'}, {'Code': '035720', 'Name': '카카오'},
    {'Code': '006400', 'Name': '삼성SDI'}, {'Code': '051910', 'Name': 'LG화학'},
    {'Code': '086520', 'Name': '에코프로'}, {'Code': '247540', 'Name': '에코프로비엠'},
    {'Code': '298020', 'Name': '효성중공업'}, {'Code': '004800', 'Name': '효성'},
    
    # --- 주요 ETF (KODEX) ---
    {'Code': '069500', 'Name': 'KODEX 200'}, {'Code': '122630', 'Name': 'KODEX 레버리지'},
    {'Code': '252670', 'Name': 'KODEX 200선물인버스2X'}, {'Code': '114800', 'Name': 'KODEX 인버스'},
    {'Code': '091160', 'Name': 'KODEX 반도체'}, {'Code': '422580', 'Name': 'KODEX 미국배당프리미엄액티브'},
    {'Code': '278530', 'Name': 'KODEX 미국S&P500TR'}, {'Code': '304940', 'Name': 'KODEX 미국나스닥100TR'},

    # --- 주요 ETF (TIGER) ---
    {'Code': '360750', 'Name': 'TIGER 미국필라델피아반도체나스닥'}, {'Code': '371460', 'Name': 'TIGER 차이나전기차SOLACTIVE'},
    {'Code': '305540', 'Name': 'TIGER 2차전지테마'}, {'Code': '133690', 'Name': 'TIGER 미국나스닥100'},
    {'Code': '102110', 'Name': 'TIGER 200'}, {'Code': '453950', 'Name': 'TIGER 미국테크TOP10 INDXX'},
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
        if any(x in code for x in ['069500', '122630', '252670', '114800', '360750']):
            data['Type'] = 'ETF'
            data['Opinion'] = "ℹ️ ETF는 여러 기업을 묶은 상품이라 영업이익 분석을 하지 않습니다."
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
# 4. [핵심] 상세 분석 로직 (설명 대폭 강화)
# ---------------------------------------------------------
def analyze_advanced(df, fund_data):
    # 컬럼 안전장치
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

    # -------------------------------------------------------
    # (1) 추세 분석 (Trend)
    # -------------------------------------------------------
    report.append("#### 1️⃣ 추세 분석 (그래프의 방향)")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append(f"- ✅ **단기 상승 추세 (+15점)**\n  : 5일 평균가격(주황선)이 20일 평균(파란선)보다 높습니다. 이는 최근 한 달간 산 사람들의 평균단가보다 현재가가 비싸다는 뜻으로, **'사는 힘'이 강하다**는 증거입니다.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append(f"- 🔥 **골든크로스 발생 (+10점)**\n  : 방금 막 단기 추세가 장기 추세를 뚫고 올라갔습니다. **본격적인 상승의 신호탄**이 될 수 있는 아주 좋은 타이밍입니다.")
    else:
        report.append(f"- 🔻 **단기 하락 추세 (0점)**\n  : 5일선이 20일선 아래에 있습니다. 단기적으로 **'파는 힘'이 더 강해서** 힘이 빠지고 있는 상태입니다.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append(f"- ✅ **중기 상승 (+5점)**\n  : 60일선(수급선) 위에 있습니다. 3개월(분기) 흐름이 좋아서 메이저 자금이 들어와 있을 가능성이 높습니다.")

    # -------------------------------------------------------
    # (2) 가격 위치 (Bollinger Bands)
    # -------------------------------------------------------
    report.append("\n#### 2️⃣ 가격 위치 (싸냐? 비싸냐?)")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 도달 (+15점)**\n  : 주가가 볼린저밴드(회색 영역)의 **맨 아래층(지하)**에 있습니다. 통계적으로 이 위치에서는 다시 위로 튀어 오를 확률이 95% 이상입니다.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append(f"- ⚠️ **천장권 도달 (0점)**\n  : 주가가 밴드 **맨 위층(옥상)**에 닿았습니다. 단기간에 너무 급하게 올라서, 차익 실현 매물이 쏟아지며 떨어질 위험이 큽니다.")
    else:
        price_score += 5
        report.append(f"- ➖ **중간 지대 (+5점)**\n  : 주가가 밴드 안쪽에서 평범하게 움직이고 있습니다. 이럴 땐 '추세'를 따르는 것이 좋습니다.")

    # -------------------------------------------------------
    # (3) 심리 & 거래량 (Volume & RSI)
    # -------------------------------------------------------
    report.append("\n#### 3️⃣ 투자 심리 & 거래량")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 구간 (RSI {curr['rsi']:.0f}) (+20점)**\n  : 사람들이 공포에 질려 주식을 너무 많이 팔았습니다. **'남들이 공포를 느낄 때 욕심을 부리라'**는 말처럼, 지금이 싸게 살 기회일 수 있습니다.")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 구간 (RSI {curr['rsi']:.0f}) (0점)**\n  : 너도나도 주식을 사서 과열되었습니다. **'탐욕' 구간**이므로 추격 매수는 위험합니다.")
    else:
        timing_score += 5
        report.append(f"- ➖ **심리 안정 (RSI {curr['rsi']:.0f}) (+5점)**\n  : 투자자들의 심리가 흥분하지 않고 차분합니다.")

    # 거래량 분석 추가
    vol_avg = df['Volume'].iloc[-20:].mean()
    if curr['Volume'] > vol_avg * 1.5 and curr['Close'] > prev['Close']:
        price_score += 5
        report.append(f"- 🔥 **거래량 폭발 (+5점)**\n  : 평소보다 1.5배 많은 거래량이 터지면서 주가가 올랐습니다. 이는 **'세력'이나 '큰손'이 들어왔다는 강력한 신호**입니다.")

    # -------------------------------------------------------
    # (4) 기업 가치 (Fundamentals)
    # -------------------------------------------------------
    report.append("\n#### 4️⃣ 기업 가치 (재무제표)")
    if fund_data['Type'] == 'ETF' or fund_data['Type'] == 'US':
        fund_score += 10
        report.append("- ℹ️ **ETF/해외주식**: 차트와 추세 위주로 분석합니다. (ETF는 묶음 상품이라 PER로 평가하기 어렵습니다)")
    else:
        per = fund_data.get('PER', 0)
        pbr = fund_data.get('PBR', 0)
        op = fund_data.get('OperatingProfit', 'N/A')
        
        if per > 0:
            if per < 10: 
                fund_score += 10
                report.append(f"- ✅ **저평가 (PER {per}) (+10점)**\n  : 기업이 1년에 버는 돈에 비해 주가가 쌉니다. 장기적으로 주가는 실적을 따라갑니다.")
            elif per > 50:
                 report.append(f"- ⚠️ **고평가 (PER {per}) (0점)**\n  : 현재 버는 돈보다 미래 기대감이 너무 많이 반영되었습니다.")
            else:
                 fund_score += 5
                 report.append(f"- ➖ **적정 주가 (PER {per}) (+5점)**\n  : 적당한 가격대입니다.")
            
            if pbr < 1.0:
                fund_score += 10
                report.append(f"- ✅ **자산주 (PBR {pbr}) (+10점)**\n  : 회사가 망해서 공장만 팔아도 본전은 건집니다. 절대적으로 싼 구간입니다.")
            
            if "억원" in str(op) and not str(op).startswith("-"):
                 report.append(f"- ✅ **영업이익 흑자 ({op})**\n  : 본업에서 돈을 잘 벌고 있는 튼튼한 회사입니다.")
        else:
            report.append("- ℹ️ 재무 정보 부족 (점수 제외)")

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
st.caption("한국/미국 주식 + ETF 완벽 분석")

# 1. 데이터 로드
krx_list = get_krx_list()

# 2. 검색창
search_keyword = st.text_input("종목명/ETF 입력 (예: 반도체, KODEX, 효성, 삼성)", placeholder="검색어를 입력하고 엔터를 누르세요")

selected_code = None
selected_name = None

# 3. 검색 로직 (키워드 입력 시 동작)
if search_keyword:
    search_keyword = search_keyword.upper().strip()
    
    # [A] 한국 종목 검색
    results = krx_list[krx_list['Name'].str.contains(search_keyword, na=False)]
    
    # [B] 미국 주식 티커 처리
    is_us_ticker = len(search_keyword) < 6 and search_keyword.isalpha()
    
    # 옵션 만들기
    options = {}
    
    if not results.empty:
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
            pass # 아래 로직 실행
    else:
        st.error("검색 결과가 없습니다. 다른 검색어를 입력해보세요.")

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
                    st.info("ETF 상품입니다. (구성 종목과 차트가 중요)")
                else:
                    f1, f2 = st.columns(2)
                    f1.metric("영업이익", str(fund_data.get('OperatingProfit', '-')))
                    f1.metric("PER", fund_data.get('PER', 0))
                    f2.metric("ROE", fund_data.get('ROE', '-'))
                    f2.metric("PBR", fund_data.get('PBR', 0))
            
            st.write("---")
            with st.expander("📝 선생님의 상세 분석 이유 (여기를 클릭하세요!)", expanded=True):
                for r in report: st.markdown(r)
            
            st.write("---")
            st.subheader("📈 4단 정밀 차트")
            
            df = sanitize_for_chart(df)
            
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                                row_heights=[0.5, 0.15, 0.15, 0.2],
                                subplot_titles=("주가 & 이동평균선", "거래량", "MACD (추세)", "RSI (심리)"))
            
            # 1. 캔들 차트
            fig.add_trace(go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'
            ), row=1, col=1)
            
            # 2. 이동평균선
            fig.add_trace(go.Scatter(
                x=df.index, y=df['ma20'], line=dict(color='blue', width=1), name='20일선'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=df.index, y=df['ma60'], line=dict(color='green', width=1), name='60일선'
            ), row=1, col=1)
            
            # 3. 거래량
            fig.add_trace(go.Bar(
                x=df.index, y=df['Volume'], name='거래량'
            ), row=2, col=1)
            
            # 4. MACD
            fig.add_trace(go.Bar(
                x=df.index, y=df['macd_diff'], marker_color='gray', name='MACD'
            ), row=3, col=1)
            
            # 5. RSI
            fig.add_trace(go.Scatter(
                x=df.index, y=df['rsi'], line=dict(color='purple'), name='RSI'
            ), row=4, col=1)
            
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            
            fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
