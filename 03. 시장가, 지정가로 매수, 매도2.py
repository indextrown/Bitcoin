import pyupbit
import time
from dotenv import load_dotenv
import os

# key 받아오기 및 업비트 객체 생성
load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY") 
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)

# 지정가 매수
# 현재가보다 0.02% 낮은 가격으로 매수 예약을 걸겠다
'''
btc_target_price = pyupbit.get_current_price("KRW-BTC") # 현재가 가져오기
btc_target_price = btc_target_price * 0.998   
won = 10000 # 원화로 10000원을 주고 싶다
print(upbit.buy_limit_order("KRW-BTC", btc_target_price, won/btc_target_price))
'''

# 알트 지정가 매수
# 지정가일 경우 거래소에서 허용하는 호가로 변경해줘야한다 즉 변환시켜줘야한다
'''
upbit.buy_limit_order("KRW-BTC", pyupbit.get_tick_size(btc_target_price), won/btc_target_price)
'''

'''
https://upbit.com/service_center/notice?id=5310
❌ 내가 지정가를 96,534,700원으로 넣었다면?
이 가격은 1,000원 단위가 아님
업비트는 2,000,000원 이상은 1,000원 단위만 허용
➜ 주문 거절됨
✅ 올바른 지정가 예시
96,534,000원 ✅
96,535,000원 ✅
96,536,000원 ✅

✅ 상황 예시 2: 알트코인 A 가격이 8,420원
❌ 내가 지정가를 8,423원으로 넣었다면?
5,000원 이상 10,000원 미만은 5원 단위만 허용
➜ 8,423원은 허용되지 않음 → 주문 실패
✅ 가능한 지정가 예시
8,420원 ✅
8,425원 ✅
8,430원 ✅

✅ 상황 예시 3: 저가코인 B 가격이 0.0237원
이 가격대는 호가 단위가 0.00001원
➜ 지정가는 반드시 아래처럼 설정해야 함
✅ 가능한 가격
0.0237 ✅
0.02371 ✅
0.02372 ✅
… 단, 소수점 5자리까지만! 0.023713 ❌
'''