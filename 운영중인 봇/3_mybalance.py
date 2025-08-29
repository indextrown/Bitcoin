import pyupbit
from dotenv import load_dotenv
import os

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
GMAIL_ADDRESS = "indextrown@gmail.com"
TO_EMAIL = "indextrown@gmail.com"

# key 받아오기 및 업비트 객체 생성
load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY") 
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD").replace(" ", "")
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)

def send_gmail(subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = TO_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        # print("✅ 메일 전송 완료")
    except Exception as e:
        print("❌ 메일 전송 실패:", e)

# 내가 매수한 (가지고 있는) 코인 개수를 리턴하는 함수
# - 원화나 드랍받은 코인(평균매입단가가 0이다) 제외!
# - 평균매입단가가 0이면 평가금액이 0이므로 구분해서 총 평가금액을 구한다.
# balances: 잔고 데이터
# return: 보유하고 있는 코인 개수
def getHasCoinCnt(balances):
    coinCnt = 0
    for value in balances:
        avg_buy_price = float(value['avg_buy_price'])
        ticker = value['unit_currency'] + "-" + value['currency']

        # 1) 원화, 드랍받은 코인(평균매입단가가 0이다) 제외!
        
        if avg_buy_price == 0:
            continue
        # 2) 거래 지원 중단된 코인 제외(현재가 조회 불가 시)
        try:
            price = pyupbit.get_current_price(ticker)
            if price is None:  
                # print(f"⚠️ 거래 지원 중단된 코인 제외: {ticker}")
                continue
        except Exception as e:
            # print(f"⚠️ {ticker} 가격 조회 실패 → 제외 ({e})")
            continue
        coinCnt += 1
    return coinCnt

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


# 내가 매수할 총 코인 개수
MAXCOINCNT = 5.0

# 처음 매수할 비중(퍼센트)
FIRSTRATE = 10.0

# 추가 매수할 비중(퍼센트)
WATERRATE = 5.0

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
# ✅ 현재 보유중인 코인 정보 추가
coinCnt = getHasCoinCnt(balances)
coinList = [value['unit_currency'] + "-" + value['currency'] 
            for value in balances if float(value['avg_buy_price']) != 0]
print("현재 보유 코인 수: ", coinCnt)
print("현재 보유 코인 목록: ", coinList)

