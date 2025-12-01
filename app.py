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
# 0. 내장 코드북 (검색 및 추천 대상)
# ---------------------------------------------------------
STATIC_KRX_DATA = [
    # [대형주/우량주]
    {'Code': '005930', 'Name': '삼성전자'}, {'Code': '000660', 'Name': 'SK하이닉스'},
    {'Code': '373220', 'Name': 'LG에너지솔루션'}, {'Code': '207940', 'Name': '삼성바이오로직스'},
    {'Code': '005380', 'Name': '현대차'}, {'Code': '000270', 'Name': '기아'},
    {'Code': '068270', 'Name': '셀트리온'}, {'Code': '005490', 'Name': 'POSCO홀딩스'},
    {'Code': '035420', 'Name': 'NAVER'}, {'Code': '035720', 'Name': '카카오'},
    {'Code': '006400', 'Name': '삼성SDI'}, {'Code': '051910', 'Name': 'LG화학'},
    {'Code': '086520', 'Name': '에코프로'}, {'Code': '247540', 'Name': '에코프로비엠'},
    {'Code': '000810', 'Name': '삼성화재'}, {'Code': '032830', 'Name': '삼성생명'},
    {'Code': '055550', 'Name': '신한지주'}, {'Code': '105560', 'Name': 'KB금융'},
    {'Code': '086790', 'Name': '하나금융지주'}, {'Code': '028260', 'Name': '삼성물산'},
    {'Code': '012330', 'Name': '현대모비스'}, {'Code': '015760', 'Name': '한국전력'},
    {'Code': '034020', 'Name': '두산에너빌리티'}, {'Code': '012450', 'Name': '한화에어로스페이스'},
    {'Code': '042700', 'Name': '한미반도체'}, {'Code': '298020', 'Name': '효성중공업'},
    {'Code': '004800', 'Name': '효성'}, {'Code': '298050', 'Name': '효성첨단소재'},
    {'Code': '010120', 'Name': 'LS일렉트릭'}, {'Code': '003550', 'Name': 'LG'},
    {'Code': '034730', 'Name': 'SK'}, {'Code': '017670', 'Name': 'SK텔레콤'},
    {'Code': '011200', 'Name': 'HMM'}, {'Code': '010950', 'Name': 'S-Oil'},
    {'Code': '003490', 'Name': '대한항공'}, {'Code': '090430', 'Name': '아모레퍼시픽'},
    
    # [ETF]
    {'Code': '069500', 'Name': 'KODEX 200'}, {'Code': '122630', 'Name': 'KODEX 레버리지'}, 
    {'Code': '114800', 'Name': 'KODEX 인버스'}, {'Code': '252670', 'Name': 'KODEX 200선물인버스2X'}, 
    {'Code': '091160', 'Name': 'KODEX 반도체'}, {'Code': '422580', 'Name': 'KODEX 미국배당프리미엄액티브'},
    {'Code': '305720', 'Name': 'KODEX 2차전지산업'}, {'Code': '455840', 'Name': 'KODEX AI반도체핵심장비'},
    {'Code': '379800', 'Name': 'KODEX 미국빅테크10(H)'}, {'Code': '304940', 'Name': 'KODEX 미국나스닥100TR'},
    {'Code': '102110', 'Name': 'TIGER 200'}, {'Code': '305540', 'Name': 'TIGER 2차전지테마'},
    {'Code': '360750', 'Name': 'TIGER 미국필라델피아반도체나스닥'}, {'Code': '371460', 'Name': 'TIGER 차이나전기차SOLACTIVE'},
    {'Code': '133690', 'Name': 'TIGER 미국나스닥100'}, {'Code': '453950', 'Name': 'TIGER 미국테크TOP10 INDXX'},
    {'Code': '411420', 'Name': 'ACE 미국S&P500'}, {'Code': '438560', 'Name': 'SOL 미국배당다우존스'}
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
# 3. 차트 데이터 (안전장치)
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
# 4. 분석 로직 (상세 설명 강화)
# ---------------------------------------------------------
def analyze_advanced(data_dict, fund_data):
    df = data_dict['D'].copy()
    for col in ['ma5', 'ma20', 'ma60', 'rsi', 'macd', 'macd_signal',
