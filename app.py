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
# 0. 인기 종목 하드코딩
# ---------------------------------------------------------
TOP_STOCKS = {
    "삼성전자": "005930", "SK하이닉스": "000660", "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940", "현대차": "005380", "기아": "000270",
    "셀트리온": "068270", "POSCO홀딩스": "005490", "NAVER": "035420",
    "카카오": "035720", "삼성SDI": "006400", "LG화학": "051910",
    "에코프로비엠": "247540", "에코프로": "086520", "두산에너빌리티": "034020",
    "한화에어로스페이스": "012450", "포스코DX": "022100", "엘앤에프": "066970"
}

# ---------------------------------------------------------
# 1. 네이버 금융 크롤링
# ---------------------------------------------------------
def get_naver_fundamental(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        
        data = {
            'PER': 0, 'PBR': 0, 'DividendYield': 0, 'Marcap': 0,
            'OperatingProfit': 'N/A', 'NetIncome': 'N/A', 'ROE': 'N/A',
            'Opinion': '데이터 없음'
        }
        
        # BeautifulSoup 파싱
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 기본 지표
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
            billion = int(parts[1].replace(',', '').strip()) * 100000000 if len(parts) > 1 else 0
            data['Marcap'] = trillion + billion
        except: pass

        # 영업이익 등 (pandas read_html 사용)
        try:
            dfs = pd.read_html(response.text, match='매출액')
            if dfs:
                fin_df = dfs[-1]
                target_col_idx = -2 
                
                op_row = fin_df[fin_df.iloc[:, 0].str.contains('영업이익', na=False)]
                if not op_row.empty:
                    data['OperatingProfit'] = str(op_row.iloc[0, target_col_idx]) + " 억원"

                ni_row = fin_df[fin_df.iloc[:, 0].str.contains('당기순이익', na=False)]
                if not ni_row.empty:
                    data['NetIncome'] = str(ni_row.iloc[0, target_col_idx]) + " 억원"
                    
                roe_row = fin_df[fin_df.iloc[:, 0].str.contains('ROE', na=False)]
                if not roe_row.empty:
                    data['ROE'] = str(roe_row.iloc[0, target_col_idx]) + " %"
        except: pass

        # 의견 생성
        opinions = []
        if data['PER'] > 0 and data['PER'] < 10: opinions.append("✅ 저평가 상태 (PER 10↓)")
        if data['PBR'] > 0 and data['PBR'] < 1.0: opinions.append("✅ 자산 가치 우수 (PBR 1↓)")
        if "억원" in data['OperatingProfit'] and not data['OperatingProfit'].startswith("-"): 
             opinions.append("✅ 영업이익 흑자")
        
        data['Opinion'] = " / ".join(opinions) if opinions else "⚠️ 중립/데이터 부족"
        return data
    except:
        return None

# ---------------------------------------------------------
# 2. 데이터 조회 및 분석
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*2)
        ticker = f"{code}.KS" if code.isdigit() else code
        
        df = fdr.DataReader(ticker, start, end)
        if (df.empty or len(df) < 10) and code.isdigit():
             df = fdr.DataReader(f"{code}.KQ", start, end)
        if df.empty:
             df = fdr.DataReader(code, start, end)
        
        if df.empty or len(df) < 60: return None, "데이터 부족"
        return df, None
    except Exception as e: return None, str(e)

def analyze_advanced(df, fund_data):
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
    report.append("#### 1️⃣ 추세 분석 (이동평균선)")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append(f"- ✅ **단기 상승 (+15점)**: 5일선 > 20일선. 매수세가 강해지고 있습니다.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append(f"- 🔥 **골든크로스 (+10점)**: 5일선이 20일선을 돌파했습니다.")
    else:
        report.append(f"- 🔻 **단기 하락 (0점)**: 5일선이 20일선 아래에 있습니다.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append(f"- ✅ **중기 상승 (+5점)**: 60일선 위에 안착해 있습니다.")
    else:
        report.append(f"- 🔻 **중기 하락 (0점)**: 60일선 아래로 처져 있습니다.")

    # 2. 가격
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 (+15점)**: 볼린저밴드 하단. 반등 가능성이 높습니다.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append(f"- ⚠️ **천장권 (0점)**: 볼린저밴드 상단. 조정 가능성이 있습니다.")
    else:
        price_score += 5
        report.append(f"- ➖ **중간 지대 (+5점)**: 밴드 중심부입니다.")

    # 3. 타이밍
    report.append("\n#### 3️⃣ 투자 심리 (RSI)")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 구간 (RSI {curr['rsi']:.1f}) (+20점)**: 너무 많이 팔았습니다. 저점 매수 기회!")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 구간 (RSI {curr['rsi']:.1f}) (0점)**: 너무 많이 샀습니다. 추격 매수 금지.")
    else:
        timing_score += 5
        report.append(f"- ➖ **중립 (RSI {curr['rsi']:.1f}) (+5점)**: 심리가 안정적입니다.")

    # 4. 가치
    report.append("\n#### 4️⃣ 펀더멘털 (가치평가)")
    per = fund_data.get('PER', 0)
    pbr = fund_data.get('PBR', 0)
    
    if per > 0:
        if per < 10: 
            fund_score += 10
            report.append(f"- ✅ **저평가 (PER {per}) (+10점)**: 이익 대비 주가가 쌉니다.")
        elif per < 25:
             fund_score += 5
             report.append(f"- ➖ **적정 (PER {per}) (+5점)**: 적당한 수준입니다.")
        else:
            report.append(f"- ⚠️ **고평가 (PER {per}) (0점)**: 다소 비싼 편입니다.")
            
        if pbr < 1.0:
            fund_score += 10
            report.append(f"- ✅ **자산가치 우수 (PBR {pbr}) (+10점)**: 청산가치보다 쌉니다.")
    else:
        report.append("- ℹ️ 재무 정보 없음 (점수 제외)")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

# ---------------------------------------------------------
# 3. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님 (완결판)")
st.caption("초보자를 위한 친절한 설명 + 네이버 실시간 재무 + 영업이익 확인")

user_input = st.text_input("🔍 종목 검색 (예: 삼성전자, 현대차, 카카오)", "")

if st.button("분석 시작", type="primary") and user_input:
    search_name = user_input.replace(" ", "").upper()
    found_code = None
    
    # 1. 인기 종목 매핑
    for name, code in TOP_STOCKS.items():
        if search_name == name or (len(search_name) >= 2 and search_name in name):
            found_code = code; search_name = name; break
            
    # 2. 검색
    if not found_code:
        try:
            listing = fdr.StockListing('KRX')
            res = listing[listing['Name'] == user_input.upper()]
            if res.empty: res = listing[listing['Name'].str.contains(user_input.upper(), na=False)]
            if not res.empty: found_code = res.iloc[0]['Code']; search_name = res.iloc[0]['Name']
        except: pass
    
    if not found_code: found_code = search_name

    # 3. 데이터 수집
    fund_data = {}
    if found_code.isdigit():
        with st.spinner("네이버 재무 정보 가져오는 중..."):
            crawled = get_naver_fundamental(found_code)
            if crawled: fund_data = crawled

    with st.spinner("차트 데이터 분석 중..."):
        raw_df, err = get_stock_data(found_code)
        if err:
            st.error(f"오류: {err}")
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # 상단 요약
            st.divider()
            st.header(f"📊 {search_name}")
            c1, c2 = st.columns([1, 1.5])
            
            with c1:
                st.metric("현재 주가", f"{int(curr_price):,}원")
                st.write(f"### 🤖 매수 확률: {score}%")
                
                if score >= 80: st.success("강력 매수 (기회!)")
                elif score >= 60: st.info("매수 고려 (긍정적)")
                elif score <= 40: st.error("관망/매도 (위험)")
                else: st.warning("중립 (대기)")
                
                if 'Opinion' in fund_data:
                    st.info(f"💡 {fund_data['Opinion']}")

            with c2:
                st.write("#### 🏢 기업 재무 (실시간)")
                if fund_data.get('Marcap', 0) > 0:
                    f1, f2 = st.columns(2)
                    f1.metric("영업이익", fund_data.get('OperatingProfit', '-'))
                    f1.metric("PER", fund_data.get('PER', 0))
                    f2.metric("ROE", fund_data.get('ROE', '-'))
                    f2.metric("PBR", fund_data.get('PBR', 0))
                else:
                    st.write("ETF 또는 데이터 없음")
            
            # 리포트
            st.write("---")
            with st.expander("📝 상세 분석 리포트 읽기", expanded=True):
                for r in report: st.markdown(r)

            # 차트
            st.write("---")
            st.subheader("📈 4단 정밀 차트")
            
            # 괄호 오류 수정된 부분
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05, 
                                row_heights=[0.5, 0.15, 0.15, 0.2],
                                subplot_titles=("가격 & 이동평균선", "거래량", "MACD (추세)", "RSI (심리)"))
            
            # Trace 추가
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue', width=1), name='20일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma60'], line=dict(color='green', width=1), name='60일선'), row=1, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='거래량'), row=2, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['macd_diff'], marker_color='gray', name='MACD'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='purple'), name='RSI'), row=4, col=1)
            
            # 기준선
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            
            fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
