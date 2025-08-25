# rsi14 30 이하일때 BTC 구매하는 봇
import pyupbit
from dotenv import load_dotenv
import os
import pandas as pd

# key 받아오기 및 업비트 객체 생성
load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY") 
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)

# RSI 계산 함수
# ohlcv: pandas DataFrame
# period: RSI 기간 (기본값: 14)
# st: 기준 날짜 (기본값: -1, 실시간 지표)
# return: RSI 값
def getRSI(ohlcv, period, st):
    delta = ohlcv["close"].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=period - 1, min_periods=period).mean()
    ma_down = down.ewm(com=period - 1, min_periods=period).mean()
    rs = ma_up / ma_down
    # .iloc[-1] 실시간 지표
    # .iloc[-2] 이전 지표
    return float(pd.Series(100 - (100 / (1 + rs)), name="RSI").iloc[st])

# 비트코인의 240분봉(캔들) 정보 가져오기
df = pyupbit.get_ohlcv("KRW-BTC", interval="minute240")

# RSI(14) 구하기
rsi14_before = getRSI(df ,14, -2)  # 이전 240분봉의(4시간 전) RSI
rsi14_now = getRSI(df ,14, -1)

if rsi14_now <= 30:
    print(upbit.buy_market_order("KRW-BTC", 5000))
