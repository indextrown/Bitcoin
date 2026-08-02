"""V4 RSI 회복 진입 봇입니다.

실행 주기는 이 파일에 두지 않습니다. 서버의 crontab이 이 스크립트를 호출하는 주기를
결정하며, 백테스트의 ``cron_interval_minutes``는 이 실거래 코드에서 읽지 않습니다.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys
import textwrap

from dotenv import load_dotenv
import pyupbit

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.notification import send_gmail  # noqa: E402
from develop.portfolio import PORTFOLIO_CONFIG, calculate_order_budget  # noqa: E402
from develop.v4.config import V4_CONFIG, interval_to_timedelta  # noqa: E402
from develop.v4.trade_logic import build_signal, decide_trade  # noqa: E402

GMAIL_ADDRESS = "indextrown@gmail.com"  # 거래 알림을 보낼 Gmail 계정입니다.
TO_EMAIL = ["indextrown@gmail.com", "wjs9643@naver.com"]  # 거래 결과를 받을 이메일 주소 목록입니다.
BASE_DIR = Path(__file__).resolve().parent  # V4 실행 코드가 있는 디렉터리입니다.
ASSET_LOG_PATH = BASE_DIR / "asset_log.csv"  # 자산·RSI 기록 CSV 파일 경로입니다.
TRADE_LOG_PATH = BASE_DIR / "trade_log.txt"  # 주문·오류 메시지 기록 파일 경로입니다.

load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")  # 업비트 API 공개 키입니다. ``.env``에서만 읽습니다.
SECRET_KEY = os.getenv("SECRET_KEY")  # 업비트 API 비밀 키입니다. ``.env``에서만 읽습니다.
GMAIL_APP_PASSWORD = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")  # Gmail 앱 비밀번호입니다.
UPBIT = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)
BASE_COIN = V4_CONFIG.ticker.split("-")[1]  # ``KRW-ETH``에서 잔고 조회에 쓸 ``ETH`` 부분입니다.


def get_account_status() -> tuple[float, float, float]:
    """업비트 잔고에서 V4 티커의 원화·코인 수량·평균 매수가를 반환합니다."""

    balances = UPBIT.get_balances()
    krw = next((float(value["balance"]) for value in balances if value["currency"] == "KRW"), 0.0)
    coin_amount = next(
        (float(value["balance"]) for value in balances if value["currency"] == BASE_COIN),
        0.0,
    )
    average_buy_price = next(
        (float(value["avg_buy_price"]) for value in balances if value["currency"] == BASE_COIN),
        0.0,
    )
    return krw, coin_amount, average_buy_price


def log_asset(timestamp: str, price: float, krw: float, coin_amount: float, rsi: float) -> float:
    """현재 자산과 RSI를 CSV 한 줄로 저장하고 원화 환산 총자산을 반환합니다."""

    total_asset = krw + coin_amount * price
    with ASSET_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"{timestamp},{price},{krw},{coin_amount},{total_asset},{rsi:.2f}\n")
    return total_asset


def log_trade(message: str) -> None:
    """주문·오류 메시지를 로그 파일에 추가하며, 로그 실패는 주문 흐름을 막지 않습니다."""

    try:
        with TRADE_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(message.strip() + "\n")
    except OSError:
        pass


def notify(subject: str, message: str) -> None:
    """콘솔·이메일·파일에 같은 거래 결과 메시지를 남깁니다."""

    print(message)
    send_gmail(subject, message, GMAIL_ADDRESS, TO_EMAIL, GMAIL_APP_PASSWORD)
    log_trade(message)


def main() -> None:
    """최신 4시간 RSI 회복 신호와 손익 기준에 따라 실제 업비트 주문을 실행합니다."""

    ohlcv = pyupbit.get_ohlcv(V4_CONFIG.ticker, interval=V4_CONFIG.interval)
    if ohlcv is None:
        print("OHLCV data is unavailable.")
        return

    try:
        signal = build_signal(ohlcv, V4_CONFIG.strategy)
    except ValueError as error:
        print(f"Signal creation failed: {error}")
        return

    krw, coin_amount, average_buy_price = get_account_status()
    v4_order_budget = calculate_order_budget(krw, PORTFOLIO_CONFIG.v4_max_capital_krw)
    decision = decide_trade(
        signal.rsi,
        signal.previous_rsi,
        krw,
        coin_amount,
        average_buy_price,
        signal.price,
        V4_CONFIG.strategy.trade,
        v4_order_budget,
    )
    candle_time = ohlcv.index[-1]
    candle_end_time = candle_time + interval_to_timedelta(V4_CONFIG.interval)

    if decision.action == "BUY":
        try:
            response = UPBIT.buy_market_order(V4_CONFIG.ticker, decision.order_amount)
            notify(
                "[V4 buy]",
                textwrap.dedent(
                    f"""
                    [V4 RSI recovery buy]
                    - ticker: {V4_CONFIG.ticker}
                    - candle: {candle_time} ~ {candle_end_time}
                    - RSI: previous {signal.previous_rsi:.2f} → current {signal.rsi:.2f}
                    - amount: {decision.order_amount:,.0f} KRW
                    - price: {signal.price:,.0f} KRW
                    - response: {response}
                    """
                ),
            )
        except Exception as error:
            notify("[V4 buy failed]", f"V4 buy error: {error}")
    elif decision.action.startswith("SELL_"):
        action_labels = {
            "SELL_STOP_LOSS": "stop loss",
            "SELL_TAKE_PROFIT": "take profit",
            "SELL_RSI": "RSI exit",
        }
        try:
            response = UPBIT.sell_market_order(V4_CONFIG.ticker, decision.order_amount)
            notify(
                f"[V4 {action_labels[decision.action]}]",
                textwrap.dedent(
                    f"""
                    [V4 {action_labels[decision.action]}]
                    - ticker: {V4_CONFIG.ticker}
                    - RSI: previous {signal.previous_rsi:.2f} → current {signal.rsi:.2f}
                    - profit rate: {decision.profit_rate:.2f}%
                    - amount: {decision.order_amount * signal.price:,.0f} KRW
                    - response: {response}
                    """
                ),
            )
        except Exception as error:
            notify("[V4 sell failed]", f"V4 sell error: {error}")
    else:
        print(f"[V4 wait] RSI={signal.previous_rsi:.2f} → {signal.rsi:.2f}, price={signal.price:,.0f}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_krw, current_coin_amount, _ = get_account_status()
    total_asset = log_asset(now, signal.price, current_krw, current_coin_amount, signal.rsi)
    print(f"[V4 asset log] {now}, total={total_asset:,.0f} KRW, RSI={signal.rsi:.2f}")


if __name__ == "__main__":
    main()
