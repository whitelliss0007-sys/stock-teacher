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
import yfinance as yf # 야후 파이낸스 추가

# 폰트 및 스타일
st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")

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
    
    # 미국 및 ETF 수동 매핑
    manual_data = [
        {'Code':'QQQ', 'Name':'Invesco QQQ', 'Market':'NASDAQ'},
        {'Code':'SPY', 'Name':'SPDR S&P 500', 'Market':'NYSE'},
        {'Code':'SOXL', 'Name':'Direxion Daily Semi Bull 3X', 'Market':'NYSE'},
        {'Code':'TSLA', 'Name':'Tesla', 'Market':'NASDAQ'},
        {'Code':'AAPL', 'Name':'Apple', 'Market':'NASDAQ'},
        {'Code':'NVDA', 'Name':'NVIDIA', 'Market':'NASDAQ'},
        {'Code':'MSFT', 'Name':'Microsoft', 'Market':'NASDAQ'},
        {'Code':'069500', 'Name':'KODEX 200', 'Market':'KOSPI'},
        {'Code':'122630', 'Name':'KODEX 레버리지', 'Market':'KOSPI'},
        {'Code':'252670', 'Name':'KODEX 200선물인버스2X', 'Market':'KOSPI'},
        {'Code':'091230', 'Name':'TIGER 반도체', 'Market':'KOSPI'},
    ]
    manual_df = pd.DataFrame(manual_data)
    
    if not krx.empty:
        cols = ['Code', 'Name', 'Market', 'Marcap', 'PER', 'PBR', 'DividendYield']
        for c in cols:
            if c not in krx.columns: krx[c] = 0
        return pd.concat([krx[cols], manual_df], ignore_index=True)
    else:
        return manual_df

@st.cache_data
def get_market_indices():
    """지수 가져오기"""
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=7)
        return {
            "kospi": fdr.DataReader('KS11', start, end).iloc[-1]['Close'],
            "kosdaq": fdr.DataReader('KQ11', start, end).iloc[-1]['Close'],
            "nasdaq": fdr.DataReader('IXIC', start, end).iloc[-1]['Close']
        }
    except:
        return None

# ---------------------------------------------------------
# 3. 데이터 조회 및 기술적 분석
# ---------------------------------------------------------
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2)
        
        ticker = code
        if code.isdigit(): ticker = f"{code}.KS"
            
        df = fdr.DataReader(ticker, start, end)
        if df.empty and code.isdigit():
             df = fdr.DataReader(f"{code}.KQ", start, end)
        if df.empty:
             df = fdr.DataReader(code, start, end)

        if df.empty or len(df) < 60:
            return None, "데이터 부족"
        return df, None
    except Exception as e:
        return None, str(e)

def analyze_advanced(df, fund_data):
    # 1. 지표 계산
    df['ma5'] = ta.trend.sma_indicator(df['Close'], window=5)
    df['ma20'] = ta.trend.sma_indicator(df['Close'], window=20)
    df['ma60'] = ta.trend.sma_indicator(df['Close'], window=60)
    
    df['rsi'] = ta.momentum.rsi(df['Close'], window=14)
    
    macd = ta.trend.MACD(df['Close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    
    bb = ta.volatility.BollingerBands(df['Close'])
    df['bb_h'] = bb.bollinger_hband()
    df['bb_l'] = bb.bollinger_lband()
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 점수 초기화
    trend_score = 0; price_score = 0; timing_score = 0; fund_score = 0
    report = []

    # (A) 추세 (30점)
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append("- ✅ **단기 상승 (+15점)**: 5일선 > 20일선")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append("- 🔥 **골든크로스 (+10점)**")
    else:
        report.append("- 🔻 **단기 하락 (0점)**")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append("- ✅ **중기 상승 (+5점)**")

    # (B) 가격위치 (20점)
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append("- ✅ **바닥권 (+15점)**: 볼린저밴드 하단")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append("- ⚠️ **천장권 (0점)**")
    else:
        price_score += 5
        report.append("- ➖ **중간 (+5점)**")
        
    # 거래량
    if curr['Volume'] > df['Volume'].iloc[-20:].mean() * 1.5 and curr['Close'] > prev['Close']:
        price_score += 5
        report.append("- 🔥 **거래량 폭발 매수 (+5점)**")

    # (C) 타이밍 (30점)
    report.append("\n#### 3️⃣ 보조지표")
    if curr['macd'] > curr['macd_signal']:
        timing_score += 10
        report.append("- ✅ **MACD 상승 (+10점)**")
    
    if curr['rsi'] < 30:
        timing_score += 20
        report.append("- 🚀 **RSI 과매도 (+20점)**: 저점 매수 기회")
    elif curr['rsi'] > 70:
        report.append("- 😱 **RSI 과매수 (0점)**: 고점 주의")
    else:
        timing_score += 5
        report.append("- ➖ **RSI 중립 (+5점)**")

    # (D) 재무 가치 (20점) - 데이터가 있을 때만
    report.append("\n#### 4️⃣ 기업 가치")
    per = fund_data.get('PER', 0)
    pbr = fund_data.get('PBR', 0)
    
    if per > 0 and pbr > 0:
        if per < 15: 
            fund_score += 10
            report.append(f"- ✅ **PER 저평가 (+10점)**: {per:.2f}")
        else:
            report.append(f"- ➖ PER: {per:.2f}")
            
        if pbr < 1.2:
            fund_score += 10
            report.append(f"- ✅ **PBR 자산가치 우수 (+10점)**: {pbr:.2f}")
        else:
            report.append(f"- ➖ PBR: {pbr:.2f}")
    else:
        report.append("- ℹ️ **ETF/해외주식/데이터없음** (점수 제외)")

    total_score = trend_score + price_score + timing_score + fund_score
    total_score = max(0, min(100, total_score))
    
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

# ---------------------------------------------------------
# 4. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
indices = get_market_indices()
if indices:
    c1, c2, c3 = st.columns(3)
    c1.metric("코스피", f"{indices['kospi']:,.2f}")
    c2.metric("코스닥", f"{indices['kosdaq']:,.2f}")
    c3.metric("나스닥", f"{indices['nasdaq']:,.2f}")

st.divider()

user_input = st.text_input("🔍 종목 검색 (예: 삼성전자, 현대차, 에코프로)", "")

if st.button("분석 시작", type="primary") and user_input:
    listing = get_stock_listing()
    search = user_input.upper().replace(" ", "")
    found_code = None; found_name = user_input; fund_data = {}
    
    if not listing.empty:
        # 이름 검색 (포함 검색)
        res = listing[listing['Name'].str.contains(search, case=False, na=False)]
        if res.empty: res = listing[listing['Code'] == search]
        
        if not res.empty:
            found_code = res.iloc[0]['Code']
            found_name = res.iloc[0]['Name']
            # 기본 데이터 복사
            fund_data = res.iloc[0].to_dict()

    if not found_code: found_code = search

    # 🚨 [핵심] 재무 데이터가 없으면 야후 파이낸스에서 가져오기 🚨
    if found_code.isdigit() and (fund_data.get('PER', 0) == 0):
        try:
            # 코스피(.KS)인지 코스닥(.KQ)인지 확인
            suffix = ".KQ" if "KOSDAQ" in str(fund_data.get('Market', '')) else ".KS"
            stock = yf.Ticker(found_code + suffix)
            info = stock.info
            
            # 데이터 채우기
            fund_data['PER'] = info.get('trailingPE', 0)
            fund_data['PBR'] = info.get('priceToBook', 0)
            fund_data['DividendYield'] = info.get('dividendRate', 0)
            fund_data['Marcap'] = info.get('marketCap', 0)
        except:
            pass
            
    with st.spinner(f"'{found_name}' 분석 중..."):
        raw_df, err = get_stock_data(found_code)
        if err:
            st.error(err)
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            
            curr_price = df.iloc[-1]['Close']
            st.header(f"{found_name}")
            st.metric("현재가", f"{int(curr_price):,}원" if str(found_code).isdigit() else f"{curr_price:.2f}$")
            
            # 점수 표시
            c1, c2 = st.columns([1, 1.5])
            with c1:
                st.write(f"## 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수")
                elif score >= 60: st.info("매수 고려")
                else: st.error("관망/매도")
                
                st.caption("--- 점수 상세 ---")
                st.write(f"📈 추세: {ts}/30")
                st.write(f"📉 가격: {ps}/20")
                st.write(f"⏱️ 타이밍: {tis}/30")
                st.write(f"💰 가치: {fs}/20")
                
            with c2:
                with st.expander("📝 분석 내용 보기", expanded=True):
                    for r in report: st.write(r)

            # 차트
            st.subheader("종합 차트")
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2])
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close']), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue'), name='20일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_l'], line=dict(color='gray', width=0), name='BB 하단'), row=1, col=1)
            
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='거래량'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], name='RSI'), row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
            fig.update_layout(height=800, xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            
            # 재무 정보
            st.divider()
            st.subheader("기업 재무 정보")
            m1, m2, m3 = st.columns(3)
            m1.metric("PER", f"{fund_data.get('PER',0):.2f}")
            m2.metric("PBR", f"{fund_data.get('PBR',0):.2f}")
            div = fund_data.get('DividendYield', 0)
            if div is None: div = 0
            m3.metric("배당수익률", f"{div:.2f}")
