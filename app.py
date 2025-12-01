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
# 0. [필수] 내장 코드북 (서버 차단 시 비상용 명부)
# ---------------------------------------------------------
STATIC_KRX_DATA = [
    # [대형주 TOP 50 & 우량주]
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
    {'Code': '298050', 'Name': '효성첨단소재'}, {'Code': '298000', 'Name': '효성티앤씨'},
    {'Code': '010120', 'Name': 'LS일렉트릭'}, {'Code': '003550', 'Name': 'LG'},
    {'Code': '034730', 'Name': 'SK'}, {'Code': '017670', 'Name': 'SK텔레콤'},
    {'Code': '011200', 'Name': 'HMM'}, {'Code': '010950', 'Name': 'S-Oil'},
    {'Code': '009150', 'Name': '삼성전기'}, {'Code': '032640', 'Name': 'LG유플러스'},
    {'Code': '003490', 'Name': '대한항공'}, {'Code': '086790', 'Name': '하나금융지주'},
    
    # [KODEX ETF]
    {'Code': '069500', 'Name': 'KODEX 200'}, {'Code': '122630', 'Name': 'KODEX 레버리지'}, 
    {'Code': '114800', 'Name': 'KODEX 인버스'}, {'Code': '252670', 'Name': 'KODEX 200선물인버스2X'}, 
    {'Code': '091160', 'Name': 'KODEX 반도체'}, {'Code': '422580', 'Name': 'KODEX 미국배당프리미엄액티브'},
    {'Code': '305720', 'Name': 'KODEX 2차전지산업'}, {'Code': '278530', 'Name': 'KODEX 200TR'},
    {'Code': '214980', 'Name': 'KODEX 단기채권Plus'}, {'Code': '455840', 'Name': 'KODEX AI반도체핵심장비'},
    {'Code': '229200', 'Name': 'KODEX 코스닥150'}, {'Code': '233740', 'Name': 'KODEX 코스닥150레버리지'},
    {'Code': '251340', 'Name': 'KODEX 코스닥150선물인버스'}, {'Code': '379800', 'Name': 'KODEX 미국빅테크10(H)'},
    {'Code': '304940', 'Name': 'KODEX 미국나스닥100TR'}, {'Code': '091170', 'Name': 'KODEX 은행'},
    {'Code': '102970', 'Name': 'KODEX 자동차'}, {'Code': '261220', 'Name': 'KODEX WTI원유선물(H)'},
    {'Code': '132030', 'Name': 'KODEX 골드선물(H)'}, {'Code': '449190', 'Name': 'KODEX K-로봇액티브'},

    # [TIGER ETF]
    {'Code': '102110', 'Name': 'TIGER 200'}, {'Code': '305540', 'Name': 'TIGER 2차전지테마'},
    {'Code': '360750', 'Name': 'TIGER 미국필라델피아반도체나스닥'}, {'Code': '371460', 'Name': 'TIGER 차이나전기차SOLACTIVE'},
    {'Code': '133690', 'Name': 'TIGER 미국나스닥100'}, {'Code': '453950', 'Name': 'TIGER 미국테크TOP10 INDXX'},
    {'Code': '327630', 'Name': 'TIGER 글로벌리튬&2차전지SOLACTIVE(합성)'}, {'Code': '465640', 'Name': 'TIGER 미국배당+7%프리미엄다우존스'},
    {'Code': '143860', 'Name': 'TIGER 헬스케어'}, {'Code': '364980', 'Name': 'TIGER KRX BBIG K-뉴딜'},
