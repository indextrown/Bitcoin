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
# return: RSI 값
def getRSI(ohlcv, period=14):
    delta = ohlcv["close"].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=period - 1, min_periods=period).mean()
    ma_down = down.ewm(com=period - 1, min_periods=period).mean()
    rs = ma_up / ma_down
    # return 100 - (100 / (1 + rs))
    return pd.Series(100 - (100 / (1 + rs)), name="RSI")

# 비트코인의 240분봉(캔들) 정보 가져오기
df = pyupbit.get_ohlcv("KRW-BTC", interval="minute240")

# 240분봉의 RSI(실시간 지표)
# print(getRSI(df).iloc[-1]) 

# 이전 240분봉의(4시간 전) RSI
# print(getRSI(df).iloc[-2])  

# 240분봉의 RSI(실시간 지표) 기준으로 30 이하면 매수 로직
rsi14 = float(getRSI(df ,14).iloc[-1])  # 실시간 240분봉의 RSI
if rsi14 < 30:
    upbit.buy_market_order("KRW-BTC", 5000)
