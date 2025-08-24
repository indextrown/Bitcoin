import pyupbit
import time
from dotenv import load_dotenv
import os

# key 받아오기 및 업비트 객체 생성
load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY") 
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)

# 시장가
# 예: KRW-BTC를 5,000원어치 시장가 매수
# upbit.buy_market_order("KRW-BTC", 5000)

# 예: 보유한 BTC 중 0.001개를 시장가로 전량 매도
# upbit.sell_market_order("KRW-BTC", 0.001)

# 지정가
# 예: KRW-BTC를 개당 50,000,000원에 0.001개 지정가 매수
# upbit.buy_limit_order("KRW-BTC", 50000000, 0.001)

# 예: KRW-BTC를 개당 60,000,000원에 0.001개 지정가 매도
# upbit.sell_limit_order("KRW-BTC", 60000000, 0.001)


'''''
# 코인 전체 정보
coins = pyupbit.get_tickers("KRW")
print(f"{'코인':<15}{'가격':>15}")
print("=" * 30)

# 매수 로직
for coin in coins:
    price = pyupbit.get_current_price(coin)
    print(f"{coin:<15}{price:>15}")
    time.sleep(0.051)

    if coin == "KRW-BTC" or coin == "KRW-ETH":
        upbit.buy_market_order(coin, 5000)  # 시장가 매수
        print(f"{coin} [구매]")
'''

# 매도 로직
# 매도의 매개변수는 가격으로 파는게 아니라 수량으로 한다. 하지만 0.00214 이렇게 팔면 불편하다
# 내 정보에서 가격을 불러와서 파는게 편하다

# 내 잔고 확인
'''
balances = upbit.get_balances()
print(f"{'코인':<10}{'보유 수량':>10}{'평균 단가':>10}{'총 매수금':>10}")
print("=" * 55)
for b in balances:
    currency = b['currency']
    unit_currency = b.get('unit_currency', 'KRW')

    # if currency == "KRW":
        # continue  # 원화는 패스

    coin = f"{unit_currency}-{currency}"
    balance = float(b['balance'])
    avg_buy_price = float(b['avg_buy_price'])
    total_buy_price = balance * avg_buy_price

    print(f"{coin:<10}{balance:>15,.8f}{avg_buy_price:>15,.0f}{total_buy_price:>15,.0f}")

# 시장가 매도 로직
btc_balance = upbit.get_balance("KRW-BTC")                    # 보유 수량 조회
print(upbit.sell_market_order("KRW-BTC", btc_balance * 0.5))  # 보유 수량의 50% 매도
'''