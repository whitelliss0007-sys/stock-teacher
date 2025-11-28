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

st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")

# ---------------------------------------------------------
# 0. [필수] 인기 종목 '이름 -> 코드' 수동 매핑 (서버 오류 방지용)
# ---------------------------------------------------------
TOP_STOCKS = {
    "삼성전자": "005930", "SK하이닉스": "000660", "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940", "현대차": "005380", "기아": "000270",
    "셀트리온": "068270", "POSCO홀딩스": "005490", "NAVER": "035420", "네이버": "035420",
    "카카오": "035720", "삼성SDI": "006400", "LG화학": "051910",
    "에코프로비엠": "247540", "에코프로": "086520", "에코프로머티": "450080",
    "두산로보틱스": "454910", "루닛": "328130", "HLB": "028300",
    "알테오젠": "196170", "HPSP": "403870", "엔켐": "348370",
    "레인보우로보틱스": "277810", "신성델타테크": "065350",
    "포스코DX": "022100", "엘앤에프": "066970", "하이브": "352820",
    "삼성물산": "028260", "KB금융": "105560", "신한지주": "055550",
    "삼성생명": "032830", "현대모비스": "012330", "SK이노베이션": "096770",
    "LG전자": "066570", "카카오뱅크": "323410", "크래프톤": "259960",
    "두산에너빌리티": "034020", "한화에어로스페이스": "012450",
    "SK텔레콤": "017670", "KT": "030200", "한국전력": "015760"
}

# ---------------------------------------------------------
# 1. 네이버 금융 직접 크롤링 (재무 데이터)
# ---------------------------------------------------------
def get_naver_fundamental(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        data = {'PER': 0, 'PBR': 0, 'DividendYield': 0, 'Marcap': 0}
        
        try: data['PER'] = float(soup.select_one('#_per').text.replace(',', ''))
        except: pass
        try: data['PBR'] = float(soup.select_one('#_pbr').text.replace(',', ''))
        except: pass
        try: data['DividendYield'] = float(soup.select_one('#_dvr').text.replace(',', ''))
        except: pass
        
        try:
            cap_text = soup.select_one('#_market_sum').text
            parts = cap_text.split('조')
            trillion = int(parts[0].replace(',', '').strip()) * 1000000000000
            if len(parts) > 1:
                billion = int(parts[1].replace(',', '').strip()) * 100000000
            else:
                billion = 0
            data['Marcap'] = trillion + billion
        except: pass
        
        return data
    except Exception as e:
        return None

# ---------------------------------------------------------
# 2. 데이터 조회 및 분석 로직
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2)
        
        # 코드가 숫자로만 되어있으면 .KS(코스피) 붙여서 시도
        ticker = f"{code}.KS" if code.isdigit() else code
        df = fdr.DataReader(ticker, start, end)
        
        # 데이터 없으면 코스닥(.KQ)으로 재시도
        if (df.empty or len(df) < 10) and code.isdigit():
             df = fdr.DataReader(f"{code}.KQ", start, end)
        
        # 그래도 없으면 그냥 코드로 시도 (ETF 등)
        if df.empty:
             df = fdr.DataReader(code, start, end)

        if df.empty or len(df) < 60: return None, "데이터 부족"
        return df, None
    except Exception as e: return None, str(e)

def analyze_advanced(df, fund_data):
    # 지표 계산
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
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    trend_score = 0; price_score = 0; timing_score = 0; fund_score = 0
    report = []

    # 1. 추세
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append("- ✅ **단기 상승 (+15점)**: 5일선 > 20일선 (정배열)")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append("- 🔥 **골든크로스 (+10점)**: 상승 신호 발생")
    else:
        report.append("- 🔻 **단기 하락 (0점)**: 5일선 < 20일선")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append("- ✅ **중기 상승 (+5점)**: 60일선 위")

    # 2. 가격위치
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append("- ✅ **바닥권 (+15점)**: 볼린저밴드 하단")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append("- ⚠️ **천장권 (0점)**: 볼린저밴드 상단")
    else:
        price_score += 5
        report.append("- ➖ **중간 (+5점)**")
        
    if curr['Volume'] > df['Volume'].iloc[-20:].mean() * 1.5 and curr['Close'] > prev['Close']:
        price_score += 5
        report.append("- 🔥 **거래량 실린 상승 (+5점)**")

    # 3. 타이밍
    report.append("\n#### 3️⃣ 보조지표")
    if curr['macd'] > curr['macd_signal']:
        timing_score += 10
        report.append("- ✅ **MACD 상승 (+10점)**")
    
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **RSI 과매도 ({curr['rsi']:.1f}) (+20점)**: 매수 기회")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **RSI 과매수 ({curr['rsi']:.1f}) (0점)**: 매도 고려")
    else:
        timing_score += 5
        report.append(f"- ➖ **RSI 중립 (+5점)**")

    # 4. 가치
    report.append("\n#### 4️⃣ 펀더멘털 (가치)")
    per = fund_data.get('PER', 0)
    pbr = fund_data.get('PBR', 0)
    
    if per > 0:
        if per < 10: 
            fund_score += 10
            report.append(f"- ✅ **PER 저평가 ({per:.2f}) (+10점)**")
        elif per < 20:
             fund_score += 5
             report.append(f"- ➖ **PER 적정 ({per:.2f}) (+5점)**")
        else:
            report.append(f"- ⚠️ **PER 고평가 ({per:.2f}) (0점)**")
            
        if pbr < 1.0:
            fund_score += 10
            report.append(f"- ✅ **PBR 저평가 ({pbr:.2f}) (+10점)**")
    else:
        report.append("- ℹ️ 재무 정보 없음 (점수 제외)")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

# ---------------------------------------------------------
# 3. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님 (완결판)")
st.caption("인기 종목 빠른 검색 + 네이버 실시간 데이터")

user_input = st.text_input("🔍 종목 검색 (예: 삼성전자, 에코프로, 카카오)", "")

if st.button("분석 시작", type="primary") and user_input:
    search_name = user_input.replace(" ", "").upper()
    found_code = None
    
    # [1] 인기 종목 리스트(TOP_STOCKS)에서 먼저 찾기 (가장 빠르고 정확함)
    # 사용자가 '삼성'만 쳐도 '삼성전자'가 나오게 처리
    for name, code in TOP_STOCKS.items():
        if search_name == name or (len(search_name) >= 2 and search_name in name):
            found_code = code
            search_name = name # 찾은 정확한 이름으로 변경
            break
            
    # [2] 인기 종목에 없으면 전체 리스트 다운로드 후 검색 (느릴 수 있음)
    if not found_code:
        try:
            listing = fdr.StockListing('KRX')
            res = listing[listing['Name'] == user_input.upper()] # 정확히 일치하는 것 우선
            if res.empty:
                 res = listing[listing['Name'].str.contains(user_input.upper(), na=False)] # 포함하는 것
            
            if not res.empty:
                found_code = res.iloc[0]['Code']
                search_name = res.iloc[0]['Name']
        except:
            pass
            
    # [3] 그래도 없으면 입력한 것을 그대로 코드로 간주 (미국주식 티커 등)
    if not found_code:
        found_code = search_name

    # --- 분석 진행 ---
    st.info(f"검색된 종목: **{search_name}** (코드: {found_code})") # 디버깅용 정보 표시

    fund_data = {'PER':0, 'PBR':0, 'Marcap':0, 'DividendYield':0}
    if found_code.isdigit():
        with st.spinner("네이버 재무 데이터 가져오는 중..."):
            crawled = get_naver_fundamental(found_code)
            if crawled: fund_data = crawled

    with st.spinner("차트 데이터 분석 중..."):
        raw_df, err = get_stock_data(found_code)
        if err:
            st.error(f"오류 발생: {err}")
            st.warning("종목명을 정확히 입력했는지 확인해주세요. (예: 삼성 -> 삼성전자)")
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # 상단 정보
            st.header(f"{search_name}")
            c1, c2 = st.columns([1, 1.5])
            with c1:
                st.metric("현재가", f"{int(curr_price):,}원")
                st.write(f"### 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수")
                elif score >= 60: st.info("매수 고려")
                else: st.error("관망/매도")
                
                st.write("---")
                st.write(f"📈 추세: {ts}/30  |  📉 가격: {ps}/20")
                st.write(f"⏱️ 타이밍: {tis}/30  |  💰 가치: {fs}/20")

            with c2:
                if fund_data['Marcap'] > 0:
                    st.success(f"""
                    **🏢 기업 정보 (실시간)**
                    - 시가총액: {fund_data['Marcap'] // 100000000:,} 억원
                    - PER: {fund_data['PER']} / PBR: {fund_data['PBR']}
                    """)
                with st.expander("📝 상세 분석 내용", expanded=True):
                    for r in report: st.markdown(r)
            
            # 차트
            st.subheader("📊 4단 정밀 차트")
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.15, 0.2],
                                subplot_titles=("가격", "거래량", "MACD", "RSI"))

            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue'), name='20일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_l'], line=dict(color='gray', width=0), fill='tonexty', fillcolor='rgba(200,200,200,0.1)', name='BB'), row=1, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='거래량'), row=2, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['macd_diff'], name='MACD'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], name='RSI'), row=4, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            
            fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
