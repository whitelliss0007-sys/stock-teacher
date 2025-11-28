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
import requests
from bs4 import BeautifulSoup

# 폰트 및 페이지 설정
st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")

# ---------------------------------------------------------
# 1. 네이버 금융 직접 크롤링 (재무 데이터 강제 확보)
# ---------------------------------------------------------
def get_naver_fundamental(code):
    """네이버 금융에서 PER, PBR, 시가총액을 직접 긁어오는 함수"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        data = {'PER': 0, 'PBR': 0, 'DividendYield': 0, 'Marcap': 0}
        
        # PER, PBR, 배당수익률 추출
        try: data['PER'] = float(soup.select_one('#_per').text.replace(',', ''))
        except: pass
        try: data['PBR'] = float(soup.select_one('#_pbr').text.replace(',', ''))
        except: pass
        try: data['DividendYield'] = float(soup.select_one('#_dvr').text.replace(',', ''))
        except: pass
        
        # 시가총액 추출 (예: "54조 1,234")
        try:
            cap_text = soup.select_one('#_market_sum').text
            # '조' 단위 처리
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
        ticker = f"{code}.KS" if code.isdigit() else code
        df = fdr.DataReader(ticker, start, end)
        
        # 코스닥 재시도
        if df.empty and code.isdigit():
             df = fdr.DataReader(f"{code}.KQ", start, end)
        
        if df.empty or len(df) < 60: return None, "데이터 부족"
        return df, None
    except Exception as e: return None, str(e)

def analyze_advanced(df, fund_data):
    # --- 지표 계산 ---
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

    # 1. 추세 분석 (30점)
    report.append("#### 1️⃣ 추세 분석 (이동평균선)")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append("- ✅ **단기 상승 추세 (+15점)**: 최근 5일 평균이 20일 평균보다 높습니다. (정배열 초기)")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append("- 🔥 **골든크로스 발생 (+10점)**: 5일선이 20일선을 방금 뚫고 올라갔습니다. 강력한 신호입니다.")
    else:
        report.append("- 🔻 **단기 하락 추세 (0점)**: 5일선이 20일선 아래에 있어 힘이 약합니다.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append("- ✅ **중기 상승 (+5점)**: 60일선(수급선) 위에 있어 3개월 추세가 든든합니다.")

    # 2. 가격 위치 (20점)
    report.append("\n#### 2️⃣ 가격 위치 (볼린저 밴드 & 거래량)")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append("- ✅ **바닥권 도달 (+15점)**: 주가가 밴드 최하단에 있어 기술적 반등이 나올 자리입니다.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append("- ⚠️ **천장권 도달 (0점)**: 주가가 밴드 최상단이라 조정받을 수 있습니다.")
    else:
        price_score += 5
        report.append("- ➖ **중간 지대 (+5점)**: 과열도 침체도 아닌 허리 구간입니다.")
        
    if curr['Volume'] > df['Volume'].iloc[-20:].mean() * 1.5 and curr['Close'] > prev['Close']:
        price_score += 5
        report.append("- 🔥 **거래량 실린 상승 (+5점)**: 거래량이 터지면서 올라가니 '진짜 상승'일 확률이 높습니다.")

    # 3. 타이밍 (30점)
    report.append("\n#### 3️⃣ 보조지표 (타이밍)")
    if curr['macd'] > curr['macd_signal']:
        timing_score += 10
        report.append("- ✅ **MACD 상승 (+10점)**: 상승 에너지가 하락 에너지보다 강합니다.")
    
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **RSI 과매도 ({curr['rsi']:.1f}) (+20점)**: 주식이 '너무 싸다'고 비명 지르는 중입니다. 줍줍 기회!")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **RSI 과매수 ({curr['rsi']:.1f}) (0점)**: 주식이 '너무 비싸다'고 합니다. 추격 매수 조심하세요.")
    else:
        timing_score += 5
        report.append(f"- ➖ **RSI 중립 ({curr['rsi']:.1f}) (+5점)**: 특별한 과열 징후는 없습니다.")

    # 4. 기업 가치 (20점)
    report.append("\n#### 4️⃣ 기업 가치 (펀더멘털)")
    per = fund_data.get('PER', 0)
    pbr = fund_data.get('PBR', 0)
    
    if per > 0 and pbr > 0:
        if per < 10: 
            fund_score += 10
            report.append(f"- ✅ **PER 저평가 ({per:.2f}) (+10점)**: 이익 대비 주가가 쌉니다. (기준 10 이하)")
        elif per < 20:
             fund_score += 5
             report.append(f"- ➖ **PER 적정 ({per:.2f}) (+5점)**: 적당한 수준입니다.")
        else:
            report.append(f"- ⚠️ **PER 고평가 ({per:.2f}) (0점)**: 이익 대비 주가가 다소 높습니다.")
            
        if pbr < 1.0:
            fund_score += 10
            report.append(f"- ✅ **PBR 자산가치 우수 ({pbr:.2f}) (+10점)**: 망해서 공장만 팔아도 본전은 건지는 가격입니다. (1.0 미만)")
        elif pbr < 3.0:
             report.append(f"- ➖ **PBR 보통 ({pbr:.2f}) (0점)**: PBR이 1~3 사이입니다.")
        else:
             report.append(f"- ⚠️ **PBR 고평가 ({pbr:.2f}) (0점)**: 자산 가치 대비 비쌉니다.")
    else:
        report.append("- ℹ️ ETF나 데이터가 없는 종목이라 가치 점수는 제외했습니다.")

    total_score = trend_score + price_score + timing_score + fund_score
    total_score = max(0, min(100, total_score))
    
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

# ---------------------------------------------------------
# 3. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님 (완결판)")
st.caption("네이버 실시간 재무 데이터 + 4단 상세 차트 적용")

user_input = st.text_input("🔍 종목 검색 (예: 현대차, 삼성전자, 카카오)", "")

if st.button("분석 시작", type="primary") and user_input:
    # 1. 종목 코드 찾기
    listing = fdr.StockListing('KRX')
    search = user_input.upper().replace(" ", "")
    found_code = None; found_name = user_input
    
    # 이름으로 찾기
    res = listing[listing['Name'].str.contains(search, case=False, na=False)]
    if res.empty: res = listing[listing['Code'] == search]
    
    if not res.empty:
        found_code = res.iloc[0]['Code']
        found_name = res.iloc[0]['Name']
    
    if not found_code: found_code = search

    # 2. 재무 데이터 크롤링 (네이버)
    fund_data = {'PER':0, 'PBR':0, 'Marcap':0, 'DividendYield':0}
    if found_code.isdigit():
        with st.spinner("네이버 증권에서 재무표 뜯어오는 중..."):
            crawled = get_naver_fundamental(found_code)
            if crawled: fund_data = crawled

    # 3. 차트 데이터 및 분석
    with st.spinner(f"'{found_name}' 차트 그리는 중..."):
        raw_df, err = get_stock_data(found_code)
        if err:
            st.error(err)
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # --- 결과 출력 ---
            st.header(f"{found_name} ({found_code})")
            c1, c2 = st.columns([1, 1.5])
            
            with c1:
                st.metric("현재가", f"{int(curr_price):,}원")
                st.write(f"### 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수 (지금 사야 함!)")
                elif score >= 60: st.info("매수 고려 (좋은 자리)")
                elif score <= 40: st.error("관망/매도 (떨어지는 칼날)")
                else: st.warning("중립 (지켜보세요)")
                
                # 점수판
                st.write("---")
                st.write(f"📈 **추세 점수:** {ts}/30")
                st.write(f"📉 **가격 위치:** {ps}/20")
                st.write(f"⏱️ **타이밍:** {tis}/30")
                st.write(f"💰 **기업 가치:** {fs}/20")
            
            with c2:
                # 기업 정보
                if fund_data['Marcap'] > 0:
                    st.info(f"""
                    **🏢 기업 정보**
                    - **시가총액:** {fund_data['Marcap'] // 100000000:,} 억원
                    - **PER:** {fund_data['PER']} (낮을수록 저평가)
                    - **PBR:** {fund_data['PBR']} (1 미만이면 쌈)
                    - **배당:** {fund_data['DividendYield']}%
                    """)
                with st.expander("📝 상세 분석 리포트 (클릭)", expanded=True):
                    for r in report: st.markdown(r)

            # --- 4단 상세 차트 ---
            st.subheader("📊 4단 정밀 분석 차트")
            
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.15, 0.2],
                                subplot_titles=("가격 & 볼린저밴드", "거래량", "MACD (추세)", "RSI (심리)"))

            # 1. 캔들 + 이평선 + 볼린저밴드
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue', width=1.5), name='20일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma60'], line=dict(color='green', width=1.5), name='60일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_h'], line=dict(color='gray', width=0), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_l'], line=dict(color='gray', width=0), fill='tonexty', fillcolor='rgba(200,200,200,0.1)', name='볼린저밴드'), row=1, col=1)

            # 2. 거래량
            colors = ['red' if row['Open'] - row['Close'] >= 0 else 'green' for index, row in df.iterrows()]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

            # 3. MACD
            fig.add_trace(go.Bar(x=df.index, y=df['macd_diff'], marker_color='silver', name='MACD 히스토그램'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['macd'], line=dict(color='black', width=1), name='MACD'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['macd_signal'], line=dict(color='red', width=1), name='Signal'), row=3, col=1)

            # 4. RSI
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='purple'), name='RSI'), row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)

            fig.update_layout(height=1000, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)
