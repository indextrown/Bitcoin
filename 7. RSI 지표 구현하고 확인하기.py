import pyupbit
from dotenv import load_dotenv
import os
import pandas as pd

# key 받아오기 및 업비트 객체 생성
load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY") 
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)

# RIS 계산 함수
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

# 비트코인의 일분봉(캔들) 정보 가져오기
df = pyupbit.get_ohlcv("KRW-BTC", interval="day")

# RSI 지표를 계산해서 프린트한다
# 오늘 지표는 계속 변하기 때문에 이를 사용할지 한칸 이전의 지표를 활용할 지 이건 전략에 따라 다르다
print(getRSI(df))

print(getRSI(df ,14).iloc[-1])  # 오늘 RSI
print(getRSI(df ,14).iloc[-2])  # 어제 RSI
print(getRSI(df ,14).iloc[-3])  # 그저께 RSI
print(getRSI(df ,14).iloc[-4])  # 4일전 RSI
print(getRSI(df ,14).iloc[-5])  # 5일전 RSI