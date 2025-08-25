'''
이 봇을 서버에서 RSI 60분봉 기준으로 RSI가 30 이하일 때 
- 15분마다 돌린다면 4번의 분할 매수를 진행하는 봇을 만들 수 있다.
- 10분마다 실행한다면 6번의 분할 매수를 진행하는 봇을 만들 수 있다.
https://class101.net/ko/classes/60dab8da41daac0014f1d4fa/lectures/60e1101c75584b000d39dd55
https://class101.net/ko/classes/60dab8da41daac0014f1d4fa/lectures/60e1102b761d260014350331



- 처음 매수할 코인
    [매수]
    - if  `이전 RSI 지표가 30 이하이고 현재 RSI 지표가 30 초과`이면서 MAXCOINCNT가 5 보다 작다면
        - firstEnterMoney 만큼매수
    
- 이미 매수한 코인(물타기)
    [매수]
    - if `이전 RSI 지표가 30 이하이고 현재 RSI 지표가 30 초과라면`
        - if 해당 코인에 할당된 최대 금액의 절반까지는
            - waterEnterMoney로 물타기
        - else (해당 코인에 할당된 최대 금액 50%초과시) && 수익률이  -5% 이하일때(원금 소진을 늦추기 위함)
            - waterEnterMoney로 물타기
    
    [매도]
    - if `현재 RSI 지표가 70 이상이면서 수익률이 1% 이상이면`
        - if 현재 코인의 매수금액이 최대 매수금액이 25% 미만이면 전체를 시장가 매도
        - else 현재 코인의 매수금액이 최대 매수금액의 25% 이상이면 절반씩 시장가 매도
    
    [매도2]
    - if 내가 가진 원금이 물탈돈보다 없으면서 수익률이 -10% 이하라면
        - 해당 코인을 절반 매도(손절)
'''

import pyupbit
from dotenv import load_dotenv
import os
import pandas as pd
import time

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

# 거래대금 상위 코인 리스트 가져오기
# interval: 캔들 간격 (minute1, minute3, minute5, minute10, minute15, minute30, minute60, minute240, day, week, month)
# top: 상위 몇 개 코인까지 가져올지 (기본값: 10)
# return: 거래대금 상위 코인 리스트
def getTopCoinList(interval, top):
    print(f"================거래대금 기준 상위 {top}개 코인 조회 중...================")

    # 거래대금이 큰 코인을 찾기 위해 정렬을 위한 딕셔너리
    dic_coin_money = dict()

    # 모든 코인 이름 가져오기
    tickers = pyupbit.get_tickers("KRW")

    # 모든 코인의 일봉(캔들) 정보 가져오기
    for ticker in tickers: 
        try:
            df = pyupbit.get_ohlcv(ticker, interval)

            # 거래대금 = 변동되는 종가 * 거래량
            # 업비트에 보이는 거래대금과는 다르다
            # - 업비트에는 24시간 기준으로 보여주고, 여기는 일봉(캔들) 기준으로 보여준다
            # 최근 2일간의 거래대금(오늘 진행중인 거래대금 + 어제 거래대금)
            volume_money = df['close'].iloc[-1] * df['volume'].iloc[-1] + df['close'].iloc[-2] * df['volume'].iloc[-2]

            # 타커를 key로, 거래대금을 value로 딕셔너리에 저장
            dic_coin_money[ticker] = volume_money 
            
            time.sleep(0.05)
        except Exception as e:
            print(e) 

    # 거래대금으로 코인 정렬
    sorted_dic_coin_money = sorted(dic_coin_money.items(), key=lambda dic_coin_money: dic_coin_money[1], reverse=True)

    # 상위 top개의 코인 리스트
    coin_list = []
    for i in range(top):
        coin_list.append(sorted_dic_coin_money[i][0])

    return coin_list

# 코인이 리스트에 있는지 확인
# coinList: 코인 리스트
# ticker: 확인할 코인 티커
# return: 리스트에 있으면 True, 없으면 False
def checkCoinInList(coinList, ticker):
    for coinTicer in coinList:
        if coinTicer == ticker:
            return True
    return False

# 티커에 해당하는 코인의 수익율을 구해서 리턴하는 함수
# balances: 잔고 데이터
# ticker: 코인 티커
# return: 수익율
def getRevenueRate(balances, ticker):
    revenue_rate = 0.0

    # 잔고 데이터 받아오기
    for value in balances:
        realTicker = value['unit_currency'] + '-' + value['currency']
        if ticker == realTicker:
            time.sleep(0.05)

            # 현재 가격을 가져옵니다.
            nowPrice = pyupbit.get_current_price(realTicker)

            # 수익율을 구해서 넣어줍니다
            revenue_rate = (nowPrice - float(value['avg_buy_price'])) * 100.0 / float(value['avg_buy_price'])
    return revenue_rate

# 티커에 해당하는 코인을 보유하고 있는지 확인하는 함수
# balances: 잔고 데이터
# ticker: 코인 티커
# return: 보유하고 있으면 True, 없으면 False
def isHasCoin(balances, ticker):
    for value in balances:
        realTicker = value['unit_currency'] + '-' + value['currency']
        if ticker == realTicker:
            return True
    return False

# #######################################################################################
# 티커에 해당하는 코인의 총 매수금액을 리턴하는 함수
# balances: 잔고 데이터
# ticker: 코인 티커
# return: 총 매수금액
def getCoinNowMoney(balances,ticker):
    CoinMoney = 0.0
    for value in balances:
        realTicker = value['unit_currency'] + "-" + value['currency']
        if ticker == realTicker:
            #해당 코인을 지정가 매도를 걸어놓으면 그 수량이 locked에 잡히게 됩니다. 
            #만약 전체 수량을 지정가 매도를 걸었다면 balance에 있던 잔고가 모두 locked로 이동하는 거죠
            #따라서 총 코인 매수 금액을 구하려면 balance + locked를 해줘야 합니다.
            CoinMoney = float(value['avg_buy_price']) * (float(value['balance']) + float(value['locked']))
            break
    return CoinMoney

# 내가 매수한 (가지고 있는) 코인 개수를 리턴하는 함수
# - 원화나 드랍받은 코인(평균매입단가가 0이다) 제외!
# - 평균매입단가가 0이면 평가금액이 0이므로 구분해서 총 평가금액을 구한다.
# balances: 잔고 데이터
# return: 보유하고 있는 코인 개수
def getHasCoinCnt(balances):
    CoinCnt = 0
    for value in balances:
        avg_buy_price = float(value['avg_buy_price'])
        if avg_buy_price != 0: #원화, 드랍받은 코인(평균매입단가가 0이다) 제외!
            CoinCnt += 1
    return CoinCnt

# getTotalMoney, getTotalRealMoney 이 두 함수를 사용하면 수익률을 구할 수 있다.
# - 업비트의 수익률은 매수한 코인들의 수익률만 모여준다. 총 자산에 대한 수익률을 이 두 함수로 만들 수 있다.
# - 내가 투자한 전체 수익률 즉 내 잔고 수익률을 구할 수 있다.
# 총 원금을 구한다!
# balances: 잔고 데이터
# return: 총 원금
def getTotalMoney(balances):
    total = 0.0
    for value in balances:
        try:
            ticker = value['currency']
            if ticker == "KRW": #원화일 때는 평균 매입 단가가 0이므로 구분해서 총 평가금액을 구한다.
                total += (float(value['balance']) + float(value['locked']))
            else:
                avg_buy_price = float(value['avg_buy_price'])

                #매수평균가(avg_buy_price)가 있으면서 잔고가 0이 아닌 코인들의 총 매수가격을 더해줍니다.
                if avg_buy_price != 0 and (float(value['balance']) != 0 or float(value['locked']) != 0):
                    #balance(잔고 수량) + locked(지정가 매도로 걸어둔 수량) 이렇게 해야 제대로 된 값이 구해집니다.
                    #지정가 매도 주문이 없다면 balance에 코인 수량이 100% 있지만 지정가 매도 주문을 걸면 그 수량만큼이 locked로 옮겨지기 때문입니다.
                    total += (avg_buy_price * (float(value['balance']) + float(value['locked'])))
        except Exception as e:
            print("GetTotalMoney error:", e)
    return total

# 총 평가금액을 구한다! 
# 위 원금을 구하는 함수와 유사하지만 코인의 매수 평균가가 아니라 현재 평가가격 기준으로 총 평가 금액을 구한다.
# balances: 잔고 데이터
# return: 총 평가금액
def getTotalRealMoney(balances):
    total = 0.0
    for value in balances:
        try:
            if value is None:
                continue

            currency = value.get("currency")
            if currency is None:
                continue

            # 원화일 경우
            if currency == "KRW":
                total += float(value.get("balance", 0)) + float(value.get("locked", 0))
                continue

            avg_buy_price = float(value.get("avg_buy_price", 0))
            balance = float(value.get("balance", 0))
            locked = float(value.get("locked", 0))

            if avg_buy_price == 0 or (balance == 0 and locked == 0):
                continue  # 원화/드랍코인 제외

            realTicker = value.get("unit_currency", "KRW") + "-" + currency
            nowPrice = pyupbit.get_current_price(realTicker)

            if nowPrice is None or nowPrice == 0:
                # 📉 상장폐지된 코인 → 평가금액 0
                print(f"⚠️ {realTicker} 상장폐지 또는 가격 조회 실패 → 평가금액 0 처리")
                continue

            total += float(nowPrice) * (balance + locked)

        except Exception as e:
           #  print(f"getTotalRealMoney error for {value}: {e}")
           continue

    return total

def getTotalRealMoney_save(balances):
    total = 0.0
    for value in balances:

        try:
            ticker = value['currency']
            if ticker == "KRW": #원화일 때는 평균 매입 단가가 0이므로 구분해서 총 평가금액을 구한다.
                total += (float(value['balance']) + float(value['locked']))
            else:
            
                avg_buy_price = float(value['avg_buy_price'])
                if avg_buy_price != 0 and (float(value['balance']) != 0 or float(value['locked']) != 0): #드랍받은 코인(평균매입단가가 0이다) 제외 하고 현재가격으로 평가금액을 구한다,.
                    realTicker = value['unit_currency'] + "-" + value['currency']

                    time.sleep(0.1)
                    nowPrice = pyupbit.get_current_price(realTicker)
                    total += (float(nowPrice) * (float(value['balance']) + float(value['locked'])))
        except Exception as e:
            print("GetTotalRealMoney error:", e)


    return total

# 내가 매수할 총 코인 개수
MAXCOINCNT = 5.0

# 처음 매수할 비중(퍼센트)
FIRSTRATE = 10.0

# 추가 매수할 비중(퍼센트)
WATERRATE = 5.0

# 추가 매수할 비용(퍼센트)

# 코인 리스트 가져오기
# tickers = pyupbit.get_tickers("KRW")

# 거래대금 상위 10개 코인 리스트 가져오기
top10_coin_list = getTopCoinList("day", 10)
print("Top 10 coins by trading volume: ", top10_coin_list)

# 위험한 코인 리스트
danger_coin_list = ['KRW-MANA', 'KRW-LOOM', 'KRW-ANKR', 'KRW-BTC']

# 내가 희망하는 코인 리스트
# lovely_coin_list = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP']

# 잔고 데이터 받아오기
balances = upbit.get_balances()


# 총 원금, 총 평가금액, 총 수익률 구하기
totalMoney = getTotalMoney(balances)
totalRealMoney = getTotalRealMoney(balances)
totalRevenue = (totalRealMoney - totalMoney) * 100.0 / totalMoney

# 코인당 최대 매수 가능한 금액
# - 100만원이고 코인 5개만 매수한다면 20만원으로 떨어짐
coinMaxMoney = totalRealMoney / MAXCOINCNT

# 할당된 코인당 최대 매수 금액에서 얼만큼씩 매수할건지
# 처음에 매수할 금액 10%(첫 진입 때는 코인당 최대 매수 가능한 금액의 10%만)
firstEnterMoney = coinMaxMoney / 100.0 * FIRSTRATE       

# 그 이후 매수할 금액 5%(두번째 진입 부터 코인당 최대 매수 가능한 금액의 5%만)
waterEnterMoney = coinMaxMoney / 100.0 * WATERRATE    

print("---------------------------------")
print("총 투자 원금(=코인 매수 원가 + 보유 KRW): ", totalMoney)
print("현재 평가금(=총 보유자산): ", totalRealMoney)
print("총 자산 수익률: ", totalRevenue)
print("---------------------------------")
print("코인당 최대 매수 금액: ", coinMaxMoney)
print("첫 매수할 금액: ", firstEnterMoney)
print("추가매수(물타기) 금액: ", waterEnterMoney)
print("---------------------------------")

 
for ticker in top10_coin_list:
    try:

        # if checkCoinInList(lovely_coin_list, ticker) == False:
        #     # 내가 희망하는 코인에 없으면 패스
        #     continue
        # 아래 top10_coin_list 코드로 대체

        # 거래대금 상위 10개 코인에 없으면 패스
        if checkCoinInList(top10_coin_list, ticker) == False:
            continue

        # 위험한 코인에 있으면 패스
        if checkCoinInList(danger_coin_list, ticker) == True:
            continue

        
        # 60분봉 정보 가져오기
        df_60 = pyupbit.get_ohlcv(ticker, "minute60")
        rsi_60_before = getRSI(df_60, 14, -2)
        rsi_60 = getRSI(df_60, 14, -1)
        print(f"ticker: {ticker}, RSI: {rsi_60_before} -> {rsi_60}")
        print(ticker)

        # 수익률 구하기
        revenue_rate = getRevenueRate(balances, ticker)
        print("revenue_rate: ", revenue_rate)

        # 원화 잔고를 가져온다
        won = float(upbit.get_balance("KRW"))
        print("현재 남은 돈(원화): ", won)
        print("---------------------------------")
        print("코인 ticker: ", ticker)
        print("최근 RSI 지표 추이: ", rsi_60_before, " -> ", rsi_60)
        print("수익률: ", revenue_rate)


        # ==========================
        # 이미 매수된 코인
        # ==========================
        # - 추가매수(물타기)
        if isHasCoin(balances, ticker) == True:

            
            # ==========================
            # [매도]
            # ==========================
            # 현재 코인의 총 매수금액
            nowCoinTotalMoney = getCoinNowMoney(balances, ticker) 

            # rsi60이 70 이상이면서 수익률이 1% 이상이면 분할 매도 진행
            if rsi_60 >= 70 and revenue_rate >= 1.0:

                # 현재 코인의 매수금액이 최대 매수금액의 25% 미만 라면 전체를 시장가 매도
                if nowCoinTotalMoney < (coinMaxMoney / 4.0):
                    print("[이미 매수된 코인 - 매도1-1]")
                    print(upbit.sell_market_order(ticker, upbit.get_balance(ticker)))
                # 현재 코인의 매수금액이 최대 매수금액의 25% 이상이면 절반씩 시장가 매도
                else:
                    print("[이미 매수된 코인 - 매도1-2]")
                    print(upbit.sell_market_order(ticker, upbit.get_balance(ticker) / 2.0))
                
                time.sleep(0.05)
                # 원화 잔고 업데이트
                won = float(upbit.get_balance("KRW"))

            # 비중 = 현재까지 매수된 금액 / 한 코인이 할당되는 최대금액 * 100
            # 즉 해당 코인에 할당된 최대 금액 기준으로 얼마나 매수했는가
            totalRate = nowCoinTotalMoney / coinMaxMoney * 100.0


            # ==========================
            # [매도2]
            # ==========================
            # [매도2 - 원금 확보]
            # 내가 가진 원금이 물탈돈보다 없고 수익률이 -10% 이하라면 해당 코인을 절반 매도(손절로직)
            if won < waterEnterMoney and revenue_rate < -10.0:
                print("[이미 매수된 코인 - 매도2] 원화 바닥 해당 코인 절반 매도합니다")
                print(upbit.sell_market_order(ticker, upbit.get_balance(ticker) / 2.0))


            # ==========================
            # [매수]
            # ==========================
            # [잔략 1]
            # if rsi_60 <= 30.0: 

            # [전략 2]
            # 60분봉 기준 RSI 지표 30 이하에서 빠져나왔을 떄 
            if rsi_60_before <= 30.0 and  rsi_60 > 30.0:

                # 총 원금에서 절반까지 다다를떄까지만 이렇게 물타기를 한다
                if totalRate <= 50.0:
                    print("[이미 매수된 코인 - 매수1-1]")
                    print(upbit.buy_market_order(ticker, waterEnterMoney))

                # 50% 초과하면
                else:
                    # 수익율이 마이너스 5% 이하일때만 매수를 진행하여 원금 소진을 늦춘다
                    if revenue_rate <= -5.0:
                        print("[이미 매수된 코인 - 매수1-2]")
                        print(upbit.buy_market_order(ticker, waterEnterMoney))








        # ==========================
        # 아직 매수안한 코인
        # ==========================
        # - 첫 매수
        else:
            # ==========================
            # [매수]
            # ==========================
            # [전략 1]
            # rei 30 이하이면서 코인이 5개 이하라면 매수 -> 이러면 너무 많은 매수 기회가 생겨서 원금이 빠르게 소진된다.
            # if rsi_60 <= 30.0 and getHasCoinCnt(balances) < MAXCOINCNT:

            # [전략 2]
            # 이전 RSI 지표가 30 이하이고 지금 RSI 지표가 30 초과이일 때 매수
            if rsi_60_before <= 30.0 and rsi_60 > 30.0 and getHasCoinCnt(balances) < MAXCOINCNT:
                print("[첫 매수]")
                print(upbit.buy_market_order(ticker, firstEnterMoney))


    except Exception as e:
        print(f"error: {e}")