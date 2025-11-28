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
# 0. 인기 종목 하드코딩 (빠른 검색용)
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
# 1. 네이버 금융 크롤링 (재무제표 상세)
# ---------------------------------------------------------
def get_naver_fundamental(code):
    """
    네이버 금융에서 PER, PBR, 영업이익, ROE 등을 긁어옵니다.
    """
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        data = {
            'PER': 0, 'PBR': 0, 'DividendYield': 0, 'Marcap': 0,
            'OperatingProfit': 'N/A', 'NetIncome': 'N/A', 'ROE': 'N/A',
            'Opinion': '데이터 없음'
        }
        
        # 1. 기본 지표 (PER, PBR, 배당, 시총)
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

        # 2. [핵심] 기업실적분석 테이블에서 영업이익 가져오기
        # pd.read_html을 사용하여 '매출액'이라는 단어가 있는 표를 찾습니다.
        try:
            dfs = pd.read_html(response.text, match='매출액')
            if dfs:
                fin_df = dfs[-1] # 보통 마지막에 매칭된 표가 실적표
                # 열(Column) 이름 정리 (최근 연도 or 분기 찾기)
                # 데이터프레임 구조상 '최근 연간 실적'의 맨 오른쪽이나 '최근 분기' 데이터를 가져옴
                # 안전하게 뒤에서 두번째 열(보통 작년 확정실적 또는 최근 추정치)을 가져옵니다.
                target_col_idx = -2 
                
                # 영업이익 (Operating Profit)
                op_row = fin_df[fin_df.iloc[:, 0].str.contains('영업이익', na=False)]
                if not op_row.empty:
                    val = op_row.iloc[0, target_col_idx]
                    data['OperatingProfit'] = str(val) + " 억원"

                # 당기순이익 (Net Income)
                ni_row = fin_df[fin_df.iloc[:, 0].str.contains('당기순이익', na=False)]
                if not ni_row.empty:
                    val = ni_row.iloc[0, target_col_idx]
                    data['NetIncome'] = str(val) + " 억원"
                    
                # ROE
                roe_row = fin_df[fin_df.iloc[:, 0].str.contains('ROE', na=False)]
                if not roe_row.empty:
                    val = roe_row.iloc[0, target_col_idx]
                    data['ROE'] = str(val) + " %"

        except Exception as e:
            pass # 테이블 파싱 실패 시 기본값 유지

        # 3. 종합 의견 생성
        opinions = []
        if data['PER'] > 0 and data['PER'] < 10: opinions.append("✅ 이익 대비 주가가 저렴합니다 (저평가).")
        if data['PBR'] > 0 and data['PBR'] < 1.0: opinions.append("✅ 청산 가치보다 쌉니다 (자산주).")
        if "억원" in data['OperatingProfit'] and not data['OperatingProfit'].startswith("-"): 
             opinions.append("✅ 영업이익이 흑자입니다 (돈을 벌고 있음).")
        
        if not opinions:
            data['Opinion'] = "⚠️ 현재 지표상으로는 뚜렷한 저평가/우량 신호가 부족하거나, 데이터가 없습니다."
        else:
            data['Opinion'] = " / ".join(opinions)

        return data
    except Exception as e:
        return None

# ---------------------------------------------------------
# 2. 데이터 조회 및 상세 분석
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

    # ----------------------------------------
    # 1. 추세 분석 (상세 설명)
    # ----------------------------------------
    report.append("#### 1️⃣ 추세 분석 (이동평균선)")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append(f"- ✅ **단기 상승 추세 (+15점)**\n  : 최근 5일간의 평균 가격이 20일(한 달) 평균보다 높습니다. 이는 최근 매수세가 강해서 주가가 위쪽으로 방향을 잡았다는 긍정적인 신호입니다.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append(f"- 🔥 **골든크로스 발생 (+10점)**\n  : 방금 막 5일선이 20일선을 뚫고 올라갔습니다. 상승 추세의 시작점일 가능성이 높습니다.")
    else:
        report.append(f"- 🔻 **단기 하락 추세 (0점)**\n  : 5일 평균 가격이 20일 평균보다 낮습니다. 단기적으로 파는 사람이 더 많아 힘이 빠지고 있는 상태입니다.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append(f"- ✅ **중기 상승 (+5점)**\n  : '수급선'이라 불리는 60일선(3개월 평균) 위에 있습니다. 중장기적인 상승 흐름은 아직 살아있습니다.")
    else:
        report.append(f"- 🔻 **중기 하락 (0점)**\n  : 주가가 60일선 아래로 처졌습니다. 3개월 동안 산 사람들이 손해를 보고 있어 매물 압박이 있을 수 있습니다.")

    # ----------------------------------------
    # 2. 가격 위치 (상세 설명)
    # ----------------------------------------
    report.append("\n#### 2️⃣ 가격 위치 (저점/고점 판단)")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append(f"- ✅ **바닥권 도달 (+15점)**\n  : 주가가 볼린저밴드(가격 변동폭)의 맨 아래층에 닿았습니다. 통계적으로 이 위치에서는 다시 튀어 오를(반등) 확률이 높습니다.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append(f"- ⚠️ **천장권 도달 (0점)**\n  : 주가가 밴드 맨 위층에 닿았습니다. 단기간에 너무 많이 올라서 조정(하락)이 나올 수 있는 위험 구간입니다.")
    else:
        price_score += 5
        report.append(f"- ➖ **중간 지대 (+5점)**\n  : 과열되지도, 너무 싸지도 않은 허리 구간입니다. 추세를 따라가는 것이 좋습니다.")

    # ----------------------------------------
    # 3. 보조지표 (심리)
    # ----------------------------------------
    report.append("\n#### 3️⃣ 투자 심리 (타이밍)")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 구간 (RSI {curr['rsi']:.1f}) (+20점)**\n  : 사람들이 공포에 질려 주식을 너무 많이 팔았습니다. 역설적으로 지금이 싸게 살 수 있는 '바겐세일' 기회일 수 있습니다.")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 구간 (RSI {curr['rsi']:.1f}) (0점)**\n  : 너도나도 주식을 사서 과열되었습니다. 탐욕이 지배하는 구간이니 추격 매수는 위험합니다.")
    else:
        timing_score += 5
        report.append(f"- ➖ **심리 중립 (RSI {curr['rsi']:.1f}) (+5점)**\n  : 투자자들의 심리가 안정적입니다. 특별한 과열 징후는 없습니다.")

    # ----------------------------------------
    # 4. 재무 가치 (펀더멘털)
    # ----------------------------------------
    report.append("\n#### 4️⃣ 기업 가치 (돈을 잘 버는가?)")
    per = fund_data.get('PER', 0)
    pbr = fund_data.get('PBR', 0)
    
    if per > 0:
        if per < 10: 
            fund_score += 10
            report.append(f"- ✅ **저평가 우량주 (PER {per}) (+10점)**\n  : 기업이 버는 돈에 비해 주가가 쌉니다 (PER 10 이하). 주가가 실적을 따라갈 가능성이 높습니다.")
        elif per > 50:
             report.append(f"- ⚠️ **고평가 성장주 (PER {per}) (0점)**\n  : 현재 버는 돈보다 주가가 훨씬 비쌉니다. 미래 성장성에 대한 기대감이 크거나, 거품일 수 있습니다.")
        else:
             fund_score += 5
             report.append(f"- ➖ **적정 주가 수준 (PER {per}) (+5점)**\n  : 이익 대비 주가가 적당한 수준입니다.")
             
        if pbr < 1.0:
            fund_score += 10
            report.append(f"- ✅ **자산 가치 우수 (PBR {pbr}) (+10점)**\n  : 회사가 망해서 가진 걸 다 팔아도 현재 주가보다 돈이 더 나옵니다. 절대적으로 싼 가격대입니다.")
    else:
        report.append("- ℹ️ 재무 정보가 부족하여 점수 계산에서 제외합니다 (ETF 등).")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

# ---------------------------------------------------------
# 3. 화면 구성
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님 (상세설명 Ver)")
st.caption("초보자를 위한 친절한 설명 + 네이버 실적 데이터 연동")

user_input = st.text_input("🔍 종목 검색 (예: 삼성전자, 카카오, 현대차)", "")

if st.button("분석 시작", type="primary") and user_input:
    search_name = user_input.replace(" ", "").upper()
    found_code = None
    
    for name, code in TOP_STOCKS.items():
        if search_name == name or (len(search_name) >= 2 and search_name in name):
            found_code = code; search_name = name; break
            
    if not found_code:
        try:
            listing = fdr.StockListing('KRX')
            res = listing[listing['Name'] == user_input.upper()]
            if res.empty: res = listing[listing['Name'].str.contains(user_input.upper(), na=False)]
            if not res.empty: found_code = res.iloc[0]['Code']; search_name = res.iloc[0]['Name']
        except: pass
    
    if not found_code: found_code = search_name

    # 분석 시작
    st.divider()
    
    fund_data = {}
    if found_code.isdigit():
        with st.spinner("네이버에서 재무제표(영업이익 등) 뜯어오는 중..."):
            crawled = get_naver_fundamental(found_code)
            if crawled: fund_data = crawled

    with st.spinner("차트 정밀 분석 중..."):
        raw_df, err = get_stock_data(found_code)
        if err:
            st.error(f"오류: {err}")
        else:
            score, report, df, ts, ps, tis, fs = analyze_advanced(raw_df, fund_data)
            curr_price = df.iloc[-1]['Close']
            
            # [섹션 1] 종합 요약
            c1, c2 = st.columns([1, 1.5])
            with c1:
                st.subheader(f"📊 {search_name}")
                st.metric("현재 주가", f"{int(curr_price):,}원")
                
                st.write(f"### 🤖 매수 확률: {score}%")
                if score >= 80: st.success("강력 매수 추천 (기회가 왔습니다!)")
                elif score >= 60: st.info("매수 고려 (긍정적 흐름)")
                elif score <= 40: st.error("관망/매도 권장 (위험 구간)")
                else: st.warning("중립 (방향성 탐색 중)")
                
                # 재무 평가 한줄평
                if 'Opinion' in fund_data:
                    st.info(f"**💡 재무 평가:** {fund_data['Opinion']}")

            with c2:
                # [섹션 2] 핵심 재무 정보 (영업이익 추가)
                st.write("#### 🏢 기업 재무 건강검진")
                if fund_data.get('Marcap', 0) > 0:
                    f1, f2 = st.columns(2)
                    f1.metric("영업이익", fund_data.get('OperatingProfit', 'N/A'))
                    f1.metric("PER (저평가척도)", fund_data.get('PER', 0))
                    f2.metric("ROE (수익성)", fund_data.get('ROE', 'N/A'))
                    f2.metric("PBR (자산가치)", fund_data.get('PBR', 0))
                    st.caption("※ 영업이익이 '적자'이거나 줄어들고 있다면 투자를 신중히 해야 합니다.")
                else:
                    st.write("ETF나 리츠는 상세 재무 데이터가 제공되지 않습니다.")

            # [섹션 3] 상세 분석 리포트
            st.write("---")
            st.subheader("📝 선생님의 상세 분석 리포트")
            with st.expander("여기를 눌러서 자세한 설명을 읽어보세요!", expanded=True):
                for r in report: st.markdown(r)

            # [섹션 4] 차트
            st.write("---")
            st.subheader("📈 4단 정밀 차트")
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05, 
                                row_heights=[0.5, 0.15, 0.15, 0.2],
                                subplot_titles=("가격 & 이동평균선", "거래량", "MACD (추세)", "RSI (심리)"))
            
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='캔들'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], line=dict(color='blue'), name='20일선'),
