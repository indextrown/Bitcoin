
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

# 이동평균선 계산 함수
# ohlcv: pandas DataFrame(분봉/일봉 정보)
# period: 이동평균 기간 (기본값: 20)
# st: 기준 날짜 (기본값: -1, 실시간 지표)
# return: 이동평균 값
def getMA(ohlcv, period, st):
    close = ohlcv['close']
    ma = close.rolling(period).mean()
    return float(ma.iloc[st])

# 비트코인의 240분봉(캔들) 정보 가져오기
df = pyupbit.get_ohlcv("KRW-BTC", interval="minute240")

# RSI(14) 구하기
rsi14_before = getRSI(df ,14, -2)  # 이전 240분봉의(4시간 전) RSI
rsi14_now = getRSI(df ,14, -1)
print("RSI(14) before: ", rsi14_before)
print("RSI(14) rsi14_now: ", rsi14_now)
print()

# MA(5) 구하기
ma5_before2 = getMA(df, 5, -3) # 8시간 전 5이동평균선
ma5_before = getMA(df, 5, -2)  # 4시간 전 240분봉의(4시간 전) 5이동평균선
ma5_now = getMA(df, 5, -1)     # 현재 240분봉의 5이동평균선
print("MA(5) before2: ", ma5_before2)
print("MA(5) before: ", ma5_before)
print("MA(5) now: ", ma5_now)
print()

# MA(20) 구하기
ma20_before2 = getMA(df, 20, -3) # 8시간 전 20이동평균선
ma20_before = getMA(df, 20, -2)  # 4시간 전 240분봉의(4시간 전) 20이동평균선
ma20_now = getMA(df, 20, -1)     # 현재 240분봉의 20이동평균선
print("MA(20) before2: ", ma20_before2)
print("MA(20) before: ", ma20_before)
print("MA(20) now: ", ma20_now)
