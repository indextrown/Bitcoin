"""V4.1 RSI 회복·추세 필터·손절 쿨다운을 실제 업비트 주문에 적용하는 봇입니다.

실행 주기는 이 파일에 두지 않습니다. 서버의 crontab이 이 스크립트를 호출하는 주기를 결정하며,
백테스트의 ``cron_interval_minutes``는 이 실거래 코드에서 읽지 않습니다.
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
from develop.v4_1.config import V4_1_CONFIG, interval_to_timedelta  # noqa: E402
from develop.v4_1.trade_logic import build_signal, decide_trade, is_uptrend  # noqa: E402
from develop.v4_1.trade_state import TradeState, load_trade_state, save_trade_state  # noqa: E402

GMAIL_ADDRESS = "indextrown@gmail.com"  # 거래 알림을 보낼 Gmail 계정입니다.
TO_EMAIL = ["indextrown@gmail.com", "wjs9643@naver.com"]  # 거래 결과를 받을 이메일 주소 목록입니다.
BASE_DIR = Path(__file__).resolve().parent  # V4.1 실행 코드가 있는 디렉터리입니다.
ASSET_LOG_PATH = BASE_DIR / "asset_log.csv"  # 자산·RSI 기록 CSV 파일 경로입니다.
TRADE_LOG_PATH = BASE_DIR / "trade_log.txt"  # 주문·오류 메시지 기록 파일 경로입니다.
TRADE_STATE_PATH = BASE_DIR / "trade_state.json"  # 손절 쿨다운을 이어갈 JSON 상태 파일 경로입니다.

load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")  # 업비트 API 공개 키입니다. ``.env``에서만 읽습니다.
SECRET_KEY = os.getenv("SECRET_KEY")  # 업비트 API 비밀 키입니다. ``.env``에서만 읽습니다.
GMAIL_APP_PASSWORD = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")  # Gmail 앱 비밀번호입니다.
UPBIT = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)
BASE_COIN = V4_1_CONFIG.ticker.split("-")[1]  # ``KRW-ETH``에서 잔고 조회에 쓸 ``ETH`` 부분입니다.


def get_account_status() -> tuple[float, float, float]:
    """업비트 잔고에서 V4.1 티커의 원화·코인 수량·평균 매수가를 반환합니다.

    Returns:
        가용 원화 잔고(KRW), 보유 코인 수량, 평균 매수가 순서의 튜플입니다.
    """

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
    """현재 자산과 RSI를 CSV 한 줄로 저장하고 원화 환산 총자산을 반환합니다.

    Args:
        timestamp: 자산을 기록한 실행 시각 문자열입니다.
        price: 보유 코인의 원화 환산에 사용할 최신 기준 가격입니다.
        krw: 현재 가용 원화 잔고입니다.
        coin_amount: 현재 보유한 대상 코인 수량입니다.
        rsi: 실행 시점에 계산한 최신 RSI입니다.

    Returns:
        원화 잔고와 코인 평가액을 합친 총자산입니다.
    """

    total_asset = krw + coin_amount * price
    with ASSET_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"{timestamp},{price},{krw},{coin_amount},{total_asset},{rsi:.2f}\n")
    return total_asset


def log_trade(message: str) -> None:
    """주문·오류 메시지를 거래 로그에 추가하며, 로그 실패는 주문 흐름을 막지 않습니다.

    Args:
        message: 파일에 기록할 주문 성공·실패 또는 오류 메시지입니다.
    """

    try:
        with TRADE_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(message.strip() + "\n")
    except OSError:
        pass


def notify(subject: str, message: str) -> None:
    """콘솔·이메일·파일에 같은 거래 결과 메시지를 남깁니다.

    Args:
        subject: Gmail 알림 제목입니다.
        message: 콘솔·이메일·거래 로그에 남길 상세 메시지입니다.
    """

    print(message)
    send_gmail(subject, message, GMAIL_ADDRESS, TO_EMAIL, GMAIL_APP_PASSWORD)
    log_trade(message)


def main() -> None:
    """최신 V4.1 신호로 실제 주문을 판단하고 손절 쿨다운 상태를 기록합니다."""

    ohlcv = pyupbit.get_ohlcv(V4_1_CONFIG.ticker, interval=V4_1_CONFIG.interval)
    if ohlcv is None:
        print("OHLCV data is unavailable.")
        return

    try:
        signal = build_signal(ohlcv, V4_1_CONFIG.strategy)
    except ValueError as error:
        print(f"Signal creation failed: {error}")
        return

    state = load_trade_state(TRADE_STATE_PATH)
    decision_time = datetime.now()
    krw, coin_amount, average_buy_price = get_account_status()
    decision = decide_trade(
        signal,
        krw,
        coin_amount,
        average_buy_price,
        decision_time,
        state.last_stop_loss_time,
        V4_1_CONFIG.strategy.trade,
    )
    candle_time = ohlcv.index[-1]
    candle_end_time = candle_time + interval_to_timedelta(V4_1_CONFIG.interval)

    if decision.action == "BUY":
        try:
            response = UPBIT.buy_market_order(V4_1_CONFIG.ticker, decision.order_amount)
            notify(
                "[V4.1 buy]",
                textwrap.dedent(
                    f"""
                    [V4.1 trend-confirmed RSI recovery buy]
                    - ticker: {V4_1_CONFIG.ticker}
                    - candle: {candle_time} ~ {candle_end_time}
                    - RSI: previous {signal.previous_rsi:.2f} → current {signal.rsi:.2f}
                    - trend: price {signal.price:,.0f} / SMA({V4_1_CONFIG.strategy.trade.trend_sma_period}) {signal.trend_sma:,.0f}
                    - amount: {decision.order_amount:,.0f} KRW
                    - response: {response}
                    """
                ),
            )
        except Exception as error:
            notify("[V4.1 buy failed]", f"V4.1 buy error: {error}")
    elif decision.action.startswith("SELL_"):
        action_labels = {
            "SELL_STOP_LOSS": "stop loss",
            "SELL_TAKE_PROFIT": "take profit",
            "SELL_RSI": "RSI exit",
        }
        try:
            response = UPBIT.sell_market_order(V4_1_CONFIG.ticker, decision.order_amount)
            if decision.action == "SELL_STOP_LOSS":
                save_trade_state(TRADE_STATE_PATH, TradeState(last_stop_loss_time=decision_time))
            notify(
                f"[V4.1 {action_labels[decision.action]}]",
                textwrap.dedent(
                    f"""
                    [V4.1 {action_labels[decision.action]}]
                    - ticker: {V4_1_CONFIG.ticker}
                    - RSI: previous {signal.previous_rsi:.2f} → current {signal.rsi:.2f}
                    - profit rate: {decision.profit_rate:.2f}%
                    - amount: {decision.order_amount * signal.price:,.0f} KRW
                    - response: {response}
                    """
                ),
            )
        except Exception as error:
            notify("[V4.1 sell failed]", f"V4.1 sell error: {error}")
    else:
        print(
            f"[V4.1 wait] RSI={signal.previous_rsi:.2f} → {signal.rsi:.2f}, "
            f"trend={'up' if is_uptrend(signal) else 'down'}, price={signal.price:,.0f}"
        )

    now = decision_time.strftime("%Y-%m-%d %H:%M:%S")
    current_krw, current_coin_amount, _ = get_account_status()
    total_asset = log_asset(now, signal.price, current_krw, current_coin_amount, signal.rsi)
    print(f"[V4.1 asset log] {now}, total={total_asset:,.0f} KRW, RSI={signal.rsi:.2f}")


if __name__ == "__main__":
    main()
