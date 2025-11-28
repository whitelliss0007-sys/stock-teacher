import ssl
# 1. SSL 보안 경고 무시
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

# 폰트 및 스타일
st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")
plt_style = {'font.family': 'sans-serif'}

# ---------------------------------------------------------
# 2. 데이터 및 리스트 확보
# ---------------------------------------------------------
@st.cache_data
def get_stock_listing():
    """전 종목 리스트 가져오기"""
    try:
        krx = fdr.StockListing('KRX') # 한국
    except:
        krx = pd.DataFrame()
    
    # 미국 및 ETF 수동 매핑 (필수 종목)
    manual_data = [
        {'Code':'QQQ', 'Name':'Invesco QQQ', 'Market':'NASDAQ'},
        {'Code':'SPY', 'Name':'SPDR S&P 500', 'Market':'NYSE'},
        {'Code':'SOXL', 'Name':'Direxion Daily Semi Bull 3X', 'Market':'NYSE'},
        {'Code':'TSLA', 'Name':'Tesla', 'Market':'NASDAQ'},
        {'Code':'AAPL', 'Name':'Apple', 'Market':'NASDAQ'},
        {'Code':'NVDA', 'Name':'NVIDIA', 'Market':'NASDAQ'},
        {'Code':'MSFT', 'Name':'Microsoft', 'Market':'NASDAQ'},
        # 한국 주요 ETF 수동 추가 (검색용)
        {'Code':'069500', 'Name':'KODEX 200', 'Market':'KOSPI'},
        {'Code':'122630', 'Name':'KODEX 레버리지', 'Market':'KOSPI'},
        {'Code':'252670', 'Name':'KODEX 200선물인버스2X', 'Market':'KOSPI'},
        {'Code':'091230', 'Name':'TIGER 반도체', 'Market':'KOSPI'},
    ]
    manual_df = pd.DataFrame(manual_data)
    
    # 합치기
    if not krx.empty:
        # 필요한 컬럼만
        cols = ['Code', 'Name', 'Market', 'Marcap', 'PER', 'PBR', 'DividendYield']
        for c in cols:
            if c not in krx.columns: krx[c] = None
        return pd.concat([krx[cols], manual_df], ignore_index=True)
    else:
        return manual_df

@st.cache_data
def get_market_indices():
    """지수 가져오기"""
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=7)
        k = fdr.DataReader('KS11', start, end).iloc[-1]
        kq = fdr.DataReader('KQ11', start, end).iloc[-1]
        ns = fdr.DataReader('IXIC', start, end).iloc[-1]
        
        def calc_chg(df): return ((df['Close'] - df['Open'])/df['Open'])*100 
        
        return {
            "kospi": (k['Close'], calc_chg(fdr.DataReader('KS11', start, end).iloc[-2:])),
            "kosdaq": (kq['Close'], calc_chg(fdr.DataReader('KQ11', start, end).iloc[-2:])),
            "nasdaq": (ns['Close'], calc_chg(fdr.DataReader('IXIC', start, end).iloc[-2:]))
        }
    except:
        return None

# ---------------------------------------------------------
# 3. 데이터 조회 및 기술적 분석 (핵심!)
# ---------------------------------------------------------
def get_stock_data(code, market=None):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2) # 2년치 데이터
        
        # 한국 주식 접미사 처리
        ticker = code
        if code.isdigit(): 
            ticker = f"{code}.KS" # 기본 시도
            
        df = fdr.DataReader(ticker, start, end)
        if df.empty and code.isdigit(): # 코스닥일수도 있으니 재시도
             df = fdr.DataReader(f"{code}.KQ", start, end)
        
        if df.empty: # 그냥 코드로 재시도 (ETF 등)
             df = fdr.DataReader(code, start, end)

        if df.empty or len(df) < 60:
            return None, "데이터가 너무 적거나 없습니다."
            
        return df, None
    except Exception as e:
        return None, str(e)

def analyze_advanced(df, fund_data):
    """초보자를 위한 상세 분석 로직 (점수 세분화)"""
    # 1. 지표 계산 (기존과 동일)
    df['ma5'] = ta.trend.sma_indicator(df['Close'], window=5)
    df['ma20'] = ta.trend.sma_indicator(df['Close'], window=20)
    df['ma60'] = ta.trend.sma_indicator(df['Close'], window=60)
    df['ma120'] = ta.trend.sma_indicator(df['Close'], window=120)
    
    df['rsi'] = ta.momentum.rsi(df['Close'], window=14)
    
    macd = ta.trend.MACD(df['Close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    
    bb = ta.volatility.BollingerBands(df['Close'])
    df['bb_h'] = bb.bollinger_hband()
    df['bb_l'] = bb.bollinger_lband()
    
    # 2. 분석 및 점수화 (현재 시점)
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 4가지 영역별 점수 초기화 (총 100점 만점)
    trend_score = 0  # 추세 점수 (Max 30점)
    price_score = 0  # 가격 위치 점수 (Max 20점)
    timing_score = 0 # 타이밍 점수 (Max 30점)
    fund_score = 0   # 기업 가치 점수 (Max 20점)
    
    report = [] # 상세 리포트 리스트

    # (A) 이동평균선 (추세) - Max 30점
    report.append("#### 1️⃣ 추세 분석 (이동평균선)")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append("- ✅ **단기 상승 추세 (+15점)**: 5일선이 20일선 위에 있습니다.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append("- 🔥 **골든크로스 발생 (+10점)**: 5일선이 20일선을 방금 뚫었습니다.")
    else:
        report.append("- 🔻 **단기 하락 추세 (0점)**: 5일선이 20일선 아래에 있습니다.")
        
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append("- ✅ **중기 상승 (+5점)**: 주가가 60일선 위에 있습니다.")
    else:
        report.append("- 🔻 **중기 하락 (0점)**: 주가가 60일선 아래에 있습니다.")
    
    # (B) 볼린저 밴드 및 거래량 (가격 위치) - Max 20점
    report.append("\n#### 2️⃣ 가격 위치 (볼린저 밴드 & 거래량)")
    
    # 가격 위치 (Max 15점)
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append("- ✅ **바닥권 도달 (+15점)**: 주가가 밴드 하단에 있어 반등 확률이 높습니다.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append("- ⚠️ **천장권 도달 (0점)**: 주가가 밴드 상단에 있어 조정 위험이 있습니다.")
    else:
        price_score += 5
        report.append("- ➖ **중간 지대 (+5점)**: 주가가 평범하게 움직이고 있습니다.")

    # 거래량 (Max 5점)
    vol_mean = df['Volume'].iloc[-20:].mean()
    if curr['Volume'] > vol_mean * 1.5:
        if curr['Close'] > prev['Close']:
            price_score += 5
            report.append("- 🔥 **거래량 폭발 (매수세, +5점)**: 주가 상승과 함께 거래량이 크게 늘었습니다.")
        else:
            report.append("- 💧 **거래량 폭발 (매도세, 0점)**: 주가 하락과 함께 거래량이 늘어 위험합니다.")
    
    # (C) 보조지표 (MACD, RSI) - Max 30점
    report.append("\n#### 3️⃣ 보조지표 (타이밍)")
    
    # MACD (Max 10점)
    if curr['macd'] > curr['macd_signal']:
        timing_score += 10
        report.append("- ✅ **MACD 상승 (+10점)**: 매수 에너지가 매도 에너지보다 셉니다.")
    
    # RSI (Max 20점)
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **RSI 과매도 ({curr['rsi']:.1f}, +20점)**: 공포에 살 기회입니다!")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **RSI 과매수 ({curr['rsi']:.1f}, 0점)**: 탐욕 구간이니 추격 매수 금지!")
    else:
        timing_score += 5
        report.append(f"- ➖ **RSI 중간 구간 (+5점)**: 중립")

    # (D) 기업 가치 (Fundamental) - Max 20점
    report.append("\n#### 4️⃣ 기업 가치 분석 (개별 종목만 반영)")
    currency = "KRW" if str(curr.name).isdigit() else "USD"
    
    # fund_data가 있고 한국 주식일 때만 점수 반영
    if fund_data is not None and currency == "KRW":
        if 'PER' in fund_data and pd.notna(fund_data['PER']) and fund_data['PER'] > 0:
            if fund_data['PER'] < 15: # PER 15 이하를 저평가로 판단 (성장주 고려)
                fund_score += 10
                report.append(f"- ✅ **PER 적정/저평가 (+10점)**: (현재 PER: {fund_data['PER']:.1f})")
            else:
                report.append(f"- 🔻 **PER 고평가 (0점)**: (현재 PER: {fund_data['PER']:.1f})")

        if 'PBR' in fund_data and pd.notna(fund_data['PBR']):
            if fund_data['PBR'] < 1.0: # PBR 1.0 이하는 자산가치 저평가
                fund_score += 10
                report.append(f"- ✅ **PBR 자산 저평가 (+10점)**: (현재 PBR: {fund_data['PBR']:.1f})")
            else:
                report.append(f"- ➖ **PBR 적정/고평가 (0점)**: (현재 PBR: {fund_data['PBR']:.1f})")
    else:
        report.append("- ℹ️ **ETF 또는 해외 주식**이라 가치 점수 계산에서 제외됩니다.")

    # 최종 점수 계산 (각 영역의 점수 합산)
    total_score = trend_score + price_score + timing_score + fund_score
    total_score = max(0, min(100, total_score)) # 0~100점 범위 유지

    return total_score, report, df, trend_score, price_score, timing_score, fund_score # 개별 점수들을 반환

# ---------------------------------------------------------
# 4. 화면 구성 (UI)
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
st.write("초보자도 이해하기 쉬운 차트와 설명을 제공합니다.")

# [지수]
indices = get_market_indices()
if indices:
    c1, c2, c3 = st.columns(3)
    # 지수 데이터가 튜플 (가격, 등락률)인지 확인하고 처리
    try:
        k_val = indices['kospi'][0]
        # 만약 Series라면 실수로 변환
        if isinstance(k_val, pd.Series): k_val = k_val.iloc[0]
        
        c1.metric("🇰🇷 코스피", f"{k_val:,.2f}")
        
        kq_val = indices['kosdaq'][0]
        if isinstance(kq_val, pd.Series): kq_val = kq_val.iloc[0]
        c2.metric("🇰🇷 코스닥", f"{kq_val:,.2f}")
        
        ns_val = indices['nasdaq'][0]
        if isinstance(ns_val, pd.Series): ns_val = ns_val.iloc[0]
        c3.metric("🇺🇸 나스닥", f"{ns_val:,.2f}")
    except:
        st.write("지수 로딩 중...")

st.divider()

# [검색]
user_input = st.text_input("🔍 종목 검색 (예: 삼성전자, 에코프로, TIGER 반도체, TSLA)", "")

if st.button("분석 시작", type="primary") and user_input:
    # 1. 종목 찾기 (만능 검색)
    listing = get_stock_listing()
    # 검색어를 대문자로 바꾸고 공백을 제거하여 검색 준비
    search = user_input.upper().replace(" ", "")
    
    found_code = None
    found_name = user_input
    fund_data = None # 재무 데이터
    
    # 1-1. KRX 리스트에서 찾기
    if not listing.empty:
        # 이름 매칭: 이름이 검색어를 포함하는지 유연하게 확인 (가장 중요한 수정)
        res = listing[listing['Name'].str.contains(search, case=False, na=False)]
        
        # '현대차'라고 검색했을 때 '현대자동차'가 포함되도록 변경됨
        if res.empty: # 2차: 코드로 시도 (코드로 검색했을 경우)
            res = listing[listing['Code'] == search]
            
        if not res.empty:
            # 매칭된 여러 개 중 첫 번째 것을 사용 (가장 정확한 것)
            found_code = res.iloc[0]['Code']
            found_name = res.iloc[0]['Name']
            fund_data = res.iloc[0]
            
    # 1-2. 못 찾았으면 미국 티커로 간주
    if not found_code:
        found_code = search
    
    # 2. 분석 시작
    with st.spinner(f"'{found_name}' 심층 분석 중입니다..."):
        # 분석 함수 호출 시, fund_data를 함께 넘겨줍니다.
        score, report, df, trend_s, price_s, timing_s, fund_s = 0, [], pd.DataFrame(), 0, 0, 0, 0
        raw_df, err = get_stock_data(found_code)
        
        if err:
            st.error(f"데이터를 가져올 수 없습니다: {err}")
        else:
            # 새로운 분석 함수 호출 (fund_data를 함께 넘김)
            score, report, df, trend_s, price_s, timing_s, fund_s = analyze_advanced(raw_df, fund_data)
            
            # --- [결과 화면] ---
            # ... (이하 결과 화면 출력 코드는 기존과 동일하게 유지됩니다.)
            
            # --- [결과 화면] ---
            curr_price = df.iloc[-1]['Close']
            currency = "KRW" if str(found_code).isdigit() else "USD"
            fmt_price = f"{int(curr_price):,}" if currency=="KRW" else f"{curr_price:.2f}"
            
            st.subheader(f"📢 {found_name} ({found_code}) 분석 리포트")
            st.markdown(f"### 현재가: **{fmt_price} {currency}**")
            
            # 1. 점수판 및 상세 분석 (출력 부분 수정)
            col1, col2 = st.columns([1, 2])
            with col1:
                st.write("### 🤖 AI 최종 매수 확률")
                st.write(f"# {score}%")
                if score >= 80: st.success("강력 매수 구간!")
                elif score >= 60: st.info("매수 고려 구간")
                elif score <= 40: st.error("매도/관망 구간")
                else: st.warning("중립 (지켜보세요)")

                st.markdown("---")
                st.markdown("### 요소별 매수 강도 (세분화)")
                
                # 점수별 퍼센트 출력 (Max score 기준)
                st.write(f"**📈 추세 점수:** **{trend_s / 30 * 100:.1f}%** ({trend_s} / 30점)")
                st.write(f"**📉 가격 위치 점수:** **{price_s / 20 * 100:.1f}%** ({price_s} / 20점)")
                st.write(f"**⏱️ 타이밍 점수:** **{timing_s / 30 * 100:.1f}%** ({timing_s} / 30점)")
                
                # ETF/해외 주식인 경우 가치 점수 0으로 표시
                if currency == "KRW" and fund_s > 0:
                    st.write(f"**💰 기업 가치 점수:** **{fund_s / 20 * 100:.1f}%** ({fund_s} / 20점)")
                elif currency == "KRW":
                    st.write(f"**💰 기업 가치 점수:** **0.0%** (재무 지표 낮음)")
                else:
                    st.write(f"**💰 기업 가치 점수:** **제외** (해외/ETF)")

            with col2:
                with st.expander("📝 상세 분석 이유 보기 (클릭)", expanded=True):
                    for line in report:
                        st.markdown(line)
            # 2. 종합 차트 (4단)
            st.subheader("📊 종합 차트 (4-in-1)")
            
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, 
                                row_heights=[0.5, 0.15, 0.15, 0.2],
                                subplot_titles=("가격 & 이평선 & 볼린저밴드", "거래량", "MACD (추세 강도)", "RSI (과열/침체)"))

            # (1) 가격 + BB + MA
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma5'], line=dict(color='orange', width=1), name='5일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue', width=1.5), name='20일선(생명선)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_h'], line=dict(color='gray', width=0), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_l'], line=dict(color='gray', width=0), fill='tonexty', fillcolor='rgba(200,200,200,0.2)', name='볼린저밴드'), row=1, col=1)

            # (2) 거래량
            colors = ['red' if row['Open'] - row['Close'] >= 0 else 'green' for index, row in df.iterrows()]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

            # (3) MACD
            fig.add_trace(go.Bar(x=df.index, y=df['macd_diff'], marker_color='silver', name='MACD Hist'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['macd'], line=dict(color='black', width=1), name='MACD'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['macd_signal'], line=dict(color='red', width=1), name='Signal'), row=3, col=1)

            # (4) RSI
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='purple', width=2), name='RSI'), row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1) # 과매수
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1) # 과매도

            fig.update_layout(height=900, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            # 3. 재무 분석 (맨 아래)
            st.divider()
            st.subheader("📑 기업 가치 평가 (재무제표)")
            if fund_data is not None and currency == "KRW":
                m1, m2, m3, m4 = st.columns(4)
                
                # 데이터 꺼내기 (안전하게)
                def get_val(k): return fund_data[k] if k in fund_data and pd.notna(fund_data[k]) else 0
                
                marcap = get_val('Marcap')
                per = get_val('PER')
                pbr = get_val('PBR')
                div = get_val('DividendYield')
                
                m1.metric("시가총액", f"{int(marcap/100000000):,} 억원")
                m2.metric("PER (저평가 척도)", f"{per}")
                m3.metric("PBR (자산가치)", f"{pbr}")
                m4.metric("배당수익률", f"{div}%")
                
                st.info("""
                💡 **재무지표 읽는 법 (초보자용)**
                - **PER**: 10보다 낮으면 '저평가(싸다)'라고 봅니다. (성장주는 높아도 됨)
                - **PBR**: 1보다 낮으면 회사가 가진 재산보다 주가가 싼 상태입니다.
                - **배당수익률**: 은행 이자보다 높으면 배당주로서 매력이 있습니다.
                """)
            else:
                st.caption("※ ETF나 해외 주식은 상세 재무 데이터(PER/PBR)가 제공되지 않습니다.")

