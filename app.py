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
import json

st.set_page_config(page_title="AI 주식 과외 선생님", layout="wide", page_icon="👨‍🏫")

# ---------------------------------------------------------
# 0. 내장 코드북 (서버 차단 시 비상용 안전장치)
# ---------------------------------------------------------
STATIC_KRX_DATA = [
    {'Code': '005930', 'Name': '삼성전자'}, {'Code': '000660', 'Name': 'SK하이닉스'},
    {'Code': '373220', 'Name': 'LG에너지솔루션'}, {'Code': '005380', 'Name': '현대차'},
    {'Code': '000270', 'Name': '기아'}, {'Code': '035420', 'Name': 'NAVER'},
    {'Code': '035720', 'Name': '카카오'}, {'Code': '069500', 'Name': 'KODEX 200'},
    {'Code': '252670', 'Name': 'KODEX 200선물인버스2X'}, {'Code': '114800', 'Name': 'KODEX 인버스'},
    {'Code': '122630', 'Name': 'KODEX 레버리지'}, {'Code': '305540', 'Name': 'TIGER 2차전지테마'},
    # (비상용으로 몇 개만 둠, 나머지는 검색으로 해결)
]

# ---------------------------------------------------------
# 1. [핵심] 네이버 만능 검색기 (토스처럼 다 찾아줌)
# ---------------------------------------------------------
def search_naver_all_matches(keyword):
    """
    검색어(예: 중소형)를 넣으면 네이버가 추천하는
    모든 연관 종목(주식, ETF) 리스트를 가져옵니다.
    """
    results = []
    try:
        # 네이버 모바일 검색 API (연관검색어 풍부함)
        url = f"https://ac.finance.naver.com/ac?q={keyword}&q_enc=euc-kr&st=111&r_format=json&r_enc=euc-kr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        data = response.json()
        
        # items[0]: 국내 종목, items[1]: 해외 종목 (있는 경우)
        if 'items' in data:
            # 국내 주식/ETF
            if len(data['items']) > 0:
                for item in data['items'][0]:
                    results.append({'Name': item[1], 'Code': item[0], 'Market': 'KR'})
            
            # 해외 주식 (네이버가 지원하는 경우)
            if len(data['items']) > 1:
                for item in data['items'][1]:
                    results.append({'Name': item[1], 'Code': item[0], 'Market': 'US'})
    except:
        pass
    
    return results

# ---------------------------------------------------------
# 2. 재무 데이터 수집
# ---------------------------------------------------------
def get_fundamental_data(code):
    data = {'PER': 0, 'PBR': 0, 'Marcap': 0, 'ROE': 'N/A', 'OperatingProfit': 'N/A', 'Type': 'KR', 'Opinion': '', 'Revenue_Trend': [], 'PSR': 0}
    
    # [한국]
    if code.isdigit():
        data['Type'] = 'KR'
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ETF 식별 (이름 확인)
            name_tag = soup.select_one('.wrap_company h2 a')
            stock_name = name_tag.text if name_tag else ""
            etf_keywords = ['ETF', 'ETN', 'KODEX', 'TIGER', 'KBSTAR', 'ACE', 'SOL', 'HANARO', 'KOSEF', 'ARIRANG', 'RISE', 'TIMEFOLIO']
            
            if any(k in stock_name.upper() for k in etf_keywords):
                data['Type'] = 'ETF'
                data['Opinion'] = "ℹ️ ETF 상품입니다. (차트/수급 분석 중심)"
                # 시가총액만 가져오고 리턴
                try:
                    cap_text = soup.select_one('#_market_sum').text
                    parts = cap_text.split('조')
                    trillion = int(parts[0].replace(',', '').strip()) * 1000000000000
                    billion = int(parts[1].replace(',', '').strip()) * 100000000 if len(parts) > 1 else 0
                    data['Marcap'] = trillion + billion
                except: pass
                return data

            # 일반 기업 데이터
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

    # [미국]
    else:
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
# 3. 차트 데이터 (안전장치)
# ---------------------------------------------------------
@st.cache_data
def get_stock_data(code):
    try:
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=365*3)
        try:
            if code.isdigit():
                df = fdr.DataReader(code, start, end)
                if df.empty: df = fdr.DataReader(f"{code}.KS", start, end)
                if df.empty: df = fdr.DataReader(f"{code}.KQ", start, end)
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
        if df.empty or len(df) < 60: return None, "데이터 부족"

        df_weekly = df.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        df_monthly = df.resample('M').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})

        return {'D': df, 'W': df_weekly, 'M': df_monthly}, None
    except Exception as e: return None, str(e)

# ---------------------------------------------------------
# 4. 분석 로직
# ---------------------------------------------------------
def analyze_advanced(data_dict, fund_data):
    df = data_dict['D'].copy()
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

    # 1. 추세
    report.append("#### 1️⃣ 추세 분석")
    if curr['ma5'] > curr['ma20']:
        trend_score += 15
        report.append("- ✅ **단기 상승 (+15점)**: 5일선 > 20일선.")
        if prev['ma5'] <= prev['ma20']:
            trend_score += 10
            report.append("- 🔥 **골든크로스 (+10점)**: 상승 전환 신호!")
    else:
        report.append("- 🔻 **단기 하락 (0점)**: 5일선 < 20일선.")
    
    if curr['Close'] > curr['ma60']:
        trend_score += 5
        report.append("- ✅ **중기 상승 (+5점)**: 60일선 위 안착.")

    # 2. 가격
    report.append("\n#### 2️⃣ 가격 위치")
    if curr['Close'] <= curr['bb_l'] * 1.02:
        price_score += 15
        report.append("- ✅ **바닥권 (+15점)**: 반등 기대.")
    elif curr['Close'] >= curr['bb_h'] * 0.98:
        report.append("- ⚠️ **천장권 (0점)**: 조정 주의.")
    else:
        price_score += 5
        report.append("- ➖ **중간 지대 (+5점)**")

    # 3. 심리
    report.append("\n#### 3️⃣ 투자 심리")
    if curr['rsi'] < 30:
        timing_score += 20
        report.append(f"- 🚀 **과매도 (RSI {curr['rsi']:.0f}) (+20점)**: 저점 매수 기회.")
    elif curr['rsi'] > 70:
        report.append(f"- 😱 **과매수 (RSI {curr['rsi']:.0f}) (0점)**: 과열 상태.")
    else:
        timing_score += 5
        report.append(f"- ➖ **안정 (RSI {curr['rsi']:.0f}) (+5점)**")

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
            if per < 15: fund_score += 5; report.append(f"- ✅ **저평가 (PER {per})**")
            elif per > 50: report.append(f"- ⚠️ **고평가 (PER {per})**")
            else: fund_score += 5; report.append(f"- ➖ **적정 (PER {per})**")
            
            if pbr < 1.2: fund_score += 5; report.append(f"- ✅ **자산주 (PBR {pbr})**")
            if psr > 0 and psr < 3.0: fund_score += 5; report.append(f"- ✅ **매출 대비 저평가 (PSR {psr})**")
            if "억원" in str(op) and not str(op).startswith("-"): report.append(f"- ✅ **영업이익 흑자**: {op}")
        else:
            report.append("- ℹ️ 재무 정보 부족")

    total_score = max(0, min(100, trend_score + price_score + timing_score + fund_score))
    return total_score, report, df, trend_score, price_score, timing_score, fund_score

def sanitize_for_chart(df):
    for col in ['ma20', 'ma60', 'bb_l', 'macd_diff', 'rsi', 'Volume']:
        if col not in df.columns: df[col] = 0.0
    return df.fillna(0)

# ---------------------------------------------------------
# 5. [신규] 우량주 발굴 로직
# ---------------------------------------------------------
def scan_undervalued_stocks():
    gems = []
    # 내장 데이터 중 일반 기업만 필터링
    target_stocks = [s for s in STATIC_KRX_DATA if 'KODEX' not in s['Name'] and 'TIGER' not in s['Name'] and 'ACE' not in s['Name']]
    
    progress_text = "보물을 찾는 중입니다... 잠시만 기다려주세요."
    my_bar = st.progress(0, text=progress_text)
    
    for i, stock in enumerate(target_stocks):
        my_bar.progress((i + 1) / len(target_stocks), text=f"🔍 분석 중: {stock['Name']}")
        try:
            f_data = get_fundamental_data(stock['Code'])
            per = f_data.get('PER', 0)
            pbr = f_data.get('PBR', 0)
            roe_str = str(f_data.get('ROE', '0')).replace('%', '').strip()
            roe = float(roe_str) if roe_str.replace('.', '', 1).isdigit() else 0
            
            reasons = []
            if 0 < per <= 15: reasons.append(f"💰 **쌉니다 (PER {per})**: 치킨집 본전 뽑는데 {per}년 걸려요.")
            if 0 < pbr <= 1.2: reasons.append(f"🏗️ **안전합니다 (PBR {pbr})**: 망해도 짐만 팔아도 본전은 건집니다.")
            if roe >= 10: reasons.append(f"👨‍🍳 **장사의 신 (ROE {roe}%)**: 사장님이 돈 굴리는 실력이 좋습니다.")
            
            op = f_data.get('OperatingProfit', 'N/A')
            if "억원" not in str(op) or str(op).startswith("-"): continue
            
            if len(reasons) >= 2:
                gems.append({'Name': stock['Name'], 'Code': stock['Code'], 'Reasons': reasons, 'Data': f_data})
        except: continue
    my_bar.empty()
    return gems

# ---------------------------------------------------------
# 6. 화면 구성 (검색 엔진 방식)
# ---------------------------------------------------------
st.title("👨‍🏫 AI 주식 과외 선생님")
tab_search, tab_recommend = st.tabs(["🔍 종목 분석", "💎 우량주 발굴"])

with tab_search:
    st.caption("한국 전 종목(ETF 포함) + 미국 주식 + PSR/매출 분석")
    search_keyword = st.text_input("종목명/ETF 입력", placeholder="중소형, 반도체, 펩트론, KODEX, 테슬라...")
    
    selected_code = None
    selected_name = None

    if search_keyword:
        search_keyword = search_keyword.strip()
        options = {}
        
        # 1. 네이버 실시간 검색 (여기가 핵심!)
        naver_results = search_naver_all_matches(search_keyword)
        
        # 2. 결과 콤보박스에 넣기
        if naver_results:
            for item in naver_results:
                # [국내] KODEX 200 (069500) 형식
                label = f"[{item['Market']}] {item['Name']} ({item['Code']})"
                options[label] = item['Code']
        
        # 3. 미국 티커 직접 입력 지원 (혹시 검색 안될 때)
        if len(search_keyword) < 6 and search_keyword.isalpha():
            options[f"[US] 미국주식: {search_keyword.upper()}"] = search_keyword.upper()

        if options:
            selected_option = st.selectbox("⬇️ 검색 결과 중 하나를 선택하세요:", list(options.keys()))
            selected_code = options[selected_option]
            
            # 이름만 예쁘게 추출 (앞의 [KR] 등 제거)
            if ']' in selected_option:
                selected_name = selected_option.split(']')[1].split('(')[0].strip()
            else:
                selected_name = selected_option
                
            if st.button("🚀 분석하기", type="primary"): pass
        else:
            st.warning("검색 결과가 없습니다.")

    # 분석 실행
    if selected_code:
        st.divider()
        st.info(f"선택된 종목: **{selected_name}** (코드: {selected_code})")
        
        fund_data = {}
        with st.spinner("재무 데이터 수집 중..."):
            fund_data = get_fundamental_data(selected_code)

        with st.spinner("차트 데이터 분석 중..."):
            data_dict, err = get_stock_data(selected_code)
            
            if err:
                st.error(f"데이터 로딩 실패: {err}")
            else:
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
                    st.write("#### 🏢 재무 요약")
                    if "ETF" in str(fund_data['Type']) or "ETF" in str(fund_data.get('Opinion')):
                        st.info(f"{fund_data.get('Opinion', 'ETF 상품입니다.')}")
                    else:
                        f1, f2 = st.columns(2)
                        f1.metric("영업이익", str(fund_data.get('OperatingProfit', '-')))
                        f1.metric("PER", fund_data.get('PER', 0))
                        f2.metric("PSR", fund_data.get('PSR', 0))
                        f2.metric("PBR", fund_data.get('PBR', 0))
                        if fund_data.get('Revenue_Trend'):
                            st.caption(f"매출 추이: {' -> '.join(fund_data['Revenue_Trend'])}")
                
                with st.expander("📝 상세 분석 내용 보기", expanded=True):
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
