# */1 * * * *      1분마다 호출
#  0 */12 * * *   12시간마다 호출

import pyupbit
import time
from dotenv import load_dotenv
import os

# key 받아오기 및 업비트 객체 생성
load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY") 
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)

# 시장가 매수
upbit.buy_market_order("KRW-BTC", 5000) 