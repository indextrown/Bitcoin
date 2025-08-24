import pyupbit
import time

coins = pyupbit.get_tickers("KRW")

print(f"{'코인':<15}{'가격':>15}")
print("=" * 30)

for coin in coins:
    price = pyupbit.get_current_price(coin)
    print(f"{coin:<15}{price:>15,.0f}")
    # print(pyupbit.get_orderbook(coin)) # 매수/매도 호가 정보
    time.sleep(0.051)

# 코인                          가격
# ==============================
# KRW-WAXP                    29
# KRW-CARV                   441
# KRW-LSK                    548
# KRW-BORA                   127
# KRW-PUNDIX                 418
# KRW-BAT                    218
# KRW-HUNT                   367
# KRW-PENGU                   49
# KRW-FIL                  3,407
# KRW-BEAM                    11
# KRW-WAVES                1,774
# KRW-USDC                 1,386
# KRW-MOVE                   182