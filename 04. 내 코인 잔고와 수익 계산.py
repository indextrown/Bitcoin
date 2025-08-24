import pyupbit
import time
from dotenv import load_dotenv
import os

# key 받아오기 및 업비트 객체 생성
load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY") 
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)

# print(upbit.get_balance("KRW")) # 원화 잔고 조회
# print(upbit.get_balances())     # 코인 잔고 조회
my_balances = upbit.get_balances()

for coin in my_balances:
    ticker = coin["currency"]

    if ticker == "KRW" or ticker == "APENFT" or ticker == "BTG" or ticker == "PDA": 
        continue

    print(f"코인: {coin['currency']}")
    print(f"보유 수량: {coin['balance']}")

    # 현재가
    now_price = pyupbit.get_current_price("KRW-" + ticker)
    print(f"현재가: {now_price}")

    # 평균매수단가
    avg_price = float(coin['avg_buy_price'])
    print(f"평균매수단가: {avg_price}")

    # 수익률 = (현재가 - 매수가) / 매수가 * 100
    revenu_rate = (now_price - avg_price) / avg_price * 100
    print(f"수익률: {revenu_rate}%")
    print()

    # 만약 수익률이 1.7이상이편 만매 로직
    '''
    if revenu_rate >= 1.7:
        upbit.sell_market_order("KRW-" + ticker, coin['balance']) # 시장가 매도
        upbit.sell_limit_order("KRW-" + ticker, pyupbit.get_tick_size(now_price * 1.002), coin['balance']) # 지정가 매도
    '''

'''
[{}, {}, {}, {}]
[{'currency': 'KRW', 'balance': '509399.51675225', 'locked': '0', 'avg_buy_price': '0', 'avg_buy_price_modified': True, 'unit_currency': 'KRW'}, 
 {'currency': 'BTG', 'balance': '0.2045707', 'locked': '0', 'avg_buy_price': '71620', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}, 
 {'currency': 'ELF', 'balance': '14.94264645', 'locked': '0', 'avg_buy_price': '538.09158215', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}, 
 {'currency': 'GAS', 'balance': '0.94526571', 'locked': '0', 'avg_buy_price': '6952.14744577', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}, 
 {'currency': 'IQ', 'balance': '633.46310522', 'locked': '0', 'avg_buy_price': '10.26542332', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'},
 {'currency': 'PDA', 'balance': '15.68000756', 'locked': '0', 'avg_buy_price': '468.9', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}, 
 {'currency': 'APENFT', 'balance': '12910.85159824', 'locked': '0', 'avg_buy_price': '0', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}, 
 {'currency': 'MINA', 'balance': '12.5513974', 'locked': '0', 'avg_buy_price': '689.7258826', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}, 
 {'currency': 'TAIKO', 'balance': '6.08059871', 'locked': '0', 'avg_buy_price': '1852.63156307', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}, 
 {'currency': 'BLAST', 'balance': '834.7210848', 'locked': '0', 'avg_buy_price': '9.49616904', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}]
 '''