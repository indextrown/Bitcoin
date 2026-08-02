# ==========================
# 환경변수 로딩 (.env)
#      ↓
# API 연결 및 초기값 설정
#      ↓
# 4시간봉 데이터 → RSI 계산
#      ↓
# 실시간 잔고 조회 (KRW, COIN, 평균단가)
#      ↓
# [조건 검사]
#   └─ RSI ≤ 30  → 매수 실행(20프로씩)
#   └─ RSI ≥ 70
#        └─ 손실/본전 → 전량 매도
#        └─ 수익 ≥ 5% → 전량 매도
#      ↓
# 모든 결과 Gmail 전송 + 자산 로그 저장(asset_log.csv)
# ==========================

# ==========================
# RSI 트레이딩 봇 + 자산/RSI 로그 저장
# ==========================

import pyupbit
from datetime import datetime
from dotenv import load_dotenv
import os
from pathlib import Path
import sys
import textwrap

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.notification import send_gmail
from develop.v3.config import V3_CONFIG, interval_to_timedelta
from develop.v3.trade_logic import build_signal, decide_trade

# ==========================
# 🔧 설정값
# ==========================
GMAIL_ADDRESS = "indextrown@gmail.com"  # 거래 알림을 보낼 Gmail 계정입니다.
TO_EMAIL = ["indextrown@gmail.com", "wjs9643@naver.com"]  # 거래 결과를 받을 이메일 주소 목록입니다.

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # V3 실행 코드가 있는 디렉터리입니다.
ASSET_LOG_PATH = os.path.join(BASE_DIR, "asset_log.csv")  # 자산·RSI 기록 CSV 파일 경로입니다.
TRADE_LOG_PATH = os.path.join(BASE_DIR, "trade_log.txt")  # 주문·오류 메시지 기록 파일 경로입니다.


# ==========================
# 🔐 API 초기화
# ==========================
load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")  # 업비트 API 공개 키입니다. ``.env``에서만 읽습니다.
SECRET_KEY = os.getenv("SECRET_KEY")  # 업비트 API 비밀 키입니다. ``.env``에서만 읽습니다.
GMAIL_APP_PASSWORD = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")  # Gmail 앱 비밀번호입니다.

upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)
BASE_COIN = V3_CONFIG.ticker.split("-")[1]  # ``KRW-ETH``에서 잔고 조회에 쓸 ``ETH`` 부분입니다.

# ==========================
# 💰 잔고 조회 함수
# ==========================
def get_account_status():
    """업비트 잔고에서 V3 티커의 원화·코인 수량·평균 매수가를 반환합니다.

    Returns:
        순서대로 가용 원화 잔고(KRW), 보유 코인 수량, 평균 매수가를 반환합니다.
    """

    balances = upbit.get_balances()
    krw = next((float(x["balance"]) for x in balances if x["currency"] == "KRW"), 0.0)
    coin_amt = next((float(x["balance"]) for x in balances if x["currency"] == BASE_COIN), 0.0)
    avg_price = next((float(x["avg_buy_price"]) for x in balances if x["currency"] == BASE_COIN), 0.0)
    return krw, coin_amt, avg_price

# ==========================
# 📊 로그 함수 (RSI 포함)
# ==========================
def log_asset(now_str, price, krw, coin_amt, rsi):
    """현재 자산과 RSI를 CSV 한 줄로 저장하고 계산된 총자산을 반환합니다.

    Args:
        now_str: 자산을 기록한 실행 시각 문자열입니다.
        price: 현재 코인 가격으로, 보유 코인을 원화로 환산할 때 사용합니다.
        krw: 현재 가용 원화 잔고입니다.
        coin_amt: 현재 보유한 대상 코인 수량입니다.
        rsi: 해당 시점에 계산한 최신 RSI 값입니다.

    Returns:
        원화 잔고와 코인 평가액을 합친 총자산입니다.
    """

    total_asset = krw + coin_amt * price
    line = f"{now_str},{price},{krw},{coin_amt},{total_asset},{rsi:.2f}\n"
    with open(ASSET_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    return total_asset

def log_trade(text):
    """주문 또는 오류 메시지를 거래 로그에 추가하며, 로그 실패는 무시합니다.

    Args:
        text: 파일에 추가할 주문 성공·실패·오류 메시지입니다.
    """

    try:
        with open(TRADE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(text.strip() + "\n")
    except Exception:
        pass

# ==========================
# 🚀 메인 실행
# ==========================
def main():
    """최신 캔들로 V3 신호를 만들고, 판단 결과에 따라 실제 주문을 실행합니다.

    실행 주기는 이 함수에 설정하지 않습니다. 실제 서버의 crontab이 이 스크립트를
    언제 호출할지 결정하며, ``BacktestConfig.cron_interval_minutes``는 사용하지
    않습니다.
    """

    df = pyupbit.get_ohlcv(V3_CONFIG.ticker, interval=V3_CONFIG.interval)
    if df is None:
        print("❌ OHLCV 데이터 부족")
        return

    try:
        signal = build_signal(df, V3_CONFIG.strategy)
    except ValueError as error:
        print(f"❌ 신호 생성 실패: {error}")
        return

    rsi = signal.rsi
    prev_rsi = signal.previous_rsi
    price = signal.price
    candle_time = df.index[-1]
    candle_end_time = candle_time + interval_to_timedelta(V3_CONFIG.interval)

    krw, coin_amt, avg_price = get_account_status()

    decision = decide_trade(rsi, krw, coin_amt, avg_price, price, V3_CONFIG.strategy.trade)

    if decision.action == "BUY":
        try:
            result = upbit.buy_market_order(V3_CONFIG.ticker, decision.order_amount)
            msg = textwrap.dedent(f"""
            [매수 성공]
            - 종목: {V3_CONFIG.ticker}
            - 기준 봉: {candle_time} ~ {candle_end_time}
            - RSI: 현재 {rsi:.2f} / 이전 {prev_rsi:.2f}
            - 매수 금액: {decision.order_amount:,.0f}원
            - 현재가: {price:,.0f}원
            - 주문 결과: {result}
            - 실행 시각: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            """)
            print(msg)
            send_gmail("[매수 성공]", msg, GMAIL_ADDRESS, TO_EMAIL, GMAIL_APP_PASSWORD)
            log_trade(msg)
        except Exception as error:
            send_gmail("[매수 실패]", f"에러: {error}", GMAIL_ADDRESS, TO_EMAIL, GMAIL_APP_PASSWORD)

    elif decision.action in {"SELL_LOSS", "SELL_PROFIT"}:
        hold_value = decision.order_amount * price
        if decision.action == "SELL_LOSS":
            success_subject = "[전량 매도]"
            failure_subject = "[전량 매도 실패]"
            message = f"""
            [전량 매도 (본전/손실)]
            - RSI: {rsi:.2f}
            - 수익률: {decision.profit_rate:.2f}%
            - 금액: {hold_value:,.0f}원
            """
        else:
            success_subject = "[익절 매도]"
            failure_subject = "[익절 매도 실패]"
            message = f"""
            [전량 매도 (익절 {decision.profit_rate:.2f}%)]
            - RSI: {rsi:.2f}
            - 금액: {hold_value:,.0f}원
            """

        try:
            result = upbit.sell_market_order(V3_CONFIG.ticker, decision.order_amount)
            msg = textwrap.dedent(message)
            print(msg)
            send_gmail(success_subject, msg, GMAIL_ADDRESS, TO_EMAIL, GMAIL_APP_PASSWORD)
            log_trade(msg)
        except Exception as error:
            send_gmail(failure_subject, f"에러: {error}", GMAIL_ADDRESS, TO_EMAIL, GMAIL_APP_PASSWORD)

    else:
        print(f"[대기] RSI={rsi:.2f}, 가격={price:,.0f}")

    # ✅ 자산 로그 (RSI 포함)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    krw_now, coin_now, _ = get_account_status()
    total_asset = log_asset(now_str, price, krw_now, coin_now, rsi)
    print(f"🧾 자산 로그 저장: {now_str}, 총자산 {total_asset:,.0f}원, RSI {rsi:.2f}")

if __name__ == "__main__":
    main()
