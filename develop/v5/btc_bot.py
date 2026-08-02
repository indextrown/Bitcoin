"""V5의 독립 단타 봇입니다.

이 파일은 V4와 동시에 실행할 필요가 없습니다. 서버의 crontab이 V5만의 실행 주기를
결정하며, ``BacktestConfig.cron_interval_minutes``는 이 실거래 코드에서 읽지 않습니다.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
import pyupbit

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.portfolio import PORTFOLIO_CONFIG, calculate_order_budget  # noqa: E402
from develop.v5.config import V5_CONFIG, validate_v5_ticker  # noqa: E402
from develop.v5.trade_logic import (  # noqa: E402
    build_signal,
    calculate_target_price,
    decide_entry,
    decide_exit,
)
from develop.v5.trade_state import ScalpState, load_trade_state, save_trade_state  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent  # V5 실행 코드와 상태 파일이 있는 디렉터리입니다.
STATE_PATH = BASE_DIR / "trade_state.json"  # 시장가 매수·지정가 매도 사이 상태를 저장할 JSON 경로입니다.
TRADE_LOG_PATH = BASE_DIR / "trade_log.txt"  # 주문·오류 메시지를 저장할 로그 파일 경로입니다.

load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")  # 업비트 API 공개 키입니다. ``.env``에서만 읽습니다.
SECRET_KEY = os.getenv("SECRET_KEY")  # 업비트 API 비밀 키입니다. ``.env``에서만 읽습니다.
UPBIT = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)
BASE_COIN = V5_CONFIG.ticker.split("-")[1]  # ``KRW-BTC``에서 잔고 조회에 사용할 ``BTC`` 부분입니다.


def log(message: str) -> None:
    """콘솔과 V5 로그 파일에 같은 메시지를 남깁니다.

    Args:
        message: 주문 결과 또는 사람이 확인해야 할 안전 관련 메시지입니다.
    """

    print(message)
    try:
        with TRADE_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(message.strip() + "\n")
    except OSError:
        pass


def get_account_status() -> tuple[float, float]:
    """업비트 잔고에서 현재 주문 가능한 원화와 V5 코인 수량을 반환합니다.

    Returns:
        주문 가능한 원화(KRW), 지정가 주문으로 잠기지 않은 V5 코인 수량입니다.
    """

    balances = UPBIT.get_balances()
    krw = next((float(value["balance"]) for value in balances if value["currency"] == "KRW"), 0.0)
    coin_amount = next(
        (float(value["balance"]) for value in balances if value["currency"] == BASE_COIN),
        0.0,
    )
    return krw, coin_amount


def _get_order(uuid: str) -> dict[str, object] | None:
    """업비트 주문 UUID를 조회하고 예기치 않은 응답은 ``None``으로 바꿉니다.

    Args:
        uuid: 시장가 매수 또는 지정가 매도의 업비트 주문 UUID입니다.

    Returns:
        주문 상세 딕셔너리 또는 조회 실패 시 ``None``입니다.
    """

    order = UPBIT.get_order(uuid)
    return order if isinstance(order, dict) else None


def _start_target_order(state: ScalpState) -> None:
    """완료된 시장가 매수 물량에 목표 순이익 지정가 매도를 등록합니다.

    Args:
        state: 완료 여부를 확인할 ``ENTRY_PENDING`` 상태입니다.
    """

    _, acquired_volume = get_account_status()
    if acquired_volume <= 0:
        log("[V5 wait] 시장가 매수 체결 수량을 아직 잔고에서 확인하지 못했습니다.")
        return
    target_price = calculate_target_price(
        state.entry_cost_krw,
        acquired_volume,
        V5_CONFIG.fee_rate,
        V5_CONFIG.strategy.trade.target_net_profit_pct,
    )
    response = UPBIT.sell_limit_order(V5_CONFIG.ticker, target_price, acquired_volume)
    if not isinstance(response, dict) or not response.get("uuid"):
        log(f"[V5 target order failed] response={response}")
        return
    entry_price = state.entry_cost_krw / acquired_volume
    save_trade_state(
        STATE_PATH,
        ScalpState(
            status="TARGET_OPEN",
            entry_order_uuid=state.entry_order_uuid,
            entry_cost_krw=state.entry_cost_krw,
            entry_time=datetime.now(),
            acquired_volume=acquired_volume,
            entry_price=entry_price,
            target_order_uuid=str(response["uuid"]),
            target_price=target_price,
        ),
    )
    log(
        f"[V5 target order] ticker={V5_CONFIG.ticker}, volume={acquired_volume:.12f}, "
        f"target={target_price:,.0f} KRW, target net={V5_CONFIG.strategy.trade.target_net_profit_pct:.2f}%"
    )


def handle_entry_pending(state: ScalpState) -> None:
    """시장가 매수 주문의 완료를 확인한 뒤 목표가 지정가 매도를 만듭니다.

    Args:
        state: 직전 실행에서 저장한 ``ENTRY_PENDING`` 상태입니다.
    """

    if not state.entry_order_uuid:
        log("[V5 safety] 매수 대기 상태에 주문 UUID가 없습니다. 수동으로 잔고를 확인하세요.")
        return
    order = _get_order(state.entry_order_uuid)
    if order is None:
        log("[V5 wait] 시장가 매수 주문을 아직 조회하지 못했습니다.")
        return
    order_state = order.get("state")
    if order_state == "done":
        _start_target_order(state)
    elif order_state in {"cancel", "reject"}:
        save_trade_state(STATE_PATH, ScalpState())
        log(f"[V5 entry cancelled] state={order_state}; 새 진입은 다음 실행부터 판단합니다.")
    else:
        log(f"[V5 wait] 시장가 매수 주문 처리 중입니다. state={order_state}")


def handle_target_open(state: ScalpState) -> None:
    """목표가 체결 여부를 확인하고, 손절·시간 청산이면 취소 요청만 등록합니다.

    취소 직후에는 지정가 주문의 잠긴 수량이 즉시 풀린다는 보장이 없으므로, 다음 독립
    크론 실행에서 ``EXIT_PENDING`` 상태를 시장가 매도로 마무리합니다.

    Args:
        state: 현재 목표가 지정가 매도가 열려 있는 ``TARGET_OPEN`` 상태입니다.
    """

    if not state.target_order_uuid or state.entry_time is None:
        log("[V5 safety] 목표가 주문 상태가 불완전합니다. 수동으로 잔고를 확인하세요.")
        return
    order = _get_order(state.target_order_uuid)
    if order is None:
        log("[V5 wait] 목표가 주문을 아직 조회하지 못했습니다.")
        return
    order_state = order.get("state")
    if order_state == "done":
        save_trade_state(STATE_PATH, ScalpState())
        log(f"[V5 target filled] ticker={V5_CONFIG.ticker}, target={state.target_price:,.0f} KRW")
        return
    if order_state != "wait":
        log(f"[V5 safety] 목표가 주문 상태가 {order_state}입니다. 수동으로 잔고를 확인하세요.")
        return

    current_price = pyupbit.get_current_price(V5_CONFIG.ticker)
    if current_price is None:
        log("[V5 wait] 현재가를 가져오지 못했습니다.")
        return
    held_minutes = (datetime.now() - state.entry_time).total_seconds() / 60
    decision = decide_exit(state.entry_price, float(current_price), held_minutes, V5_CONFIG.strategy.trade)
    if decision.action == "WAIT":
        log(
            f"[V5 wait] price={float(current_price):,.0f}, target={state.target_price:,.0f}, "
            f"held={held_minutes:.0f}m"
        )
        return
    response = UPBIT.cancel_order(state.target_order_uuid)
    save_trade_state(
        STATE_PATH,
        ScalpState(
            status="EXIT_PENDING",
            entry_order_uuid=state.entry_order_uuid,
            entry_cost_krw=state.entry_cost_krw,
            entry_time=state.entry_time,
            acquired_volume=state.acquired_volume,
            entry_price=state.entry_price,
            target_order_uuid=state.target_order_uuid,
            target_price=state.target_price,
        ),
    )
    log(f"[V5 {decision.action}] target cancellation requested. response={response}")


def handle_exit_pending(state: ScalpState) -> None:
    """취소되어 풀린 V5 물량을 시장가로 매도해 손절·시간 청산을 완료합니다.

    Args:
        state: 목표가 주문 취소 뒤 시장가 매도를 기다리는 ``EXIT_PENDING`` 상태입니다.
    """

    _, coin_amount = get_account_status()
    current_price = pyupbit.get_current_price(V5_CONFIG.ticker)
    if current_price is None or coin_amount * float(current_price) < V5_CONFIG.strategy.trade.min_trade_krw:
        log("[V5 wait] 취소한 지정가 물량이 아직 시장가 매도 가능 상태가 아닙니다.")
        return
    response = UPBIT.sell_market_order(V5_CONFIG.ticker, coin_amount)
    if not isinstance(response, dict) or not response.get("uuid"):
        log(f"[V5 exit failed] response={response}")
        return
    save_trade_state(STATE_PATH, ScalpState())
    log(f"[V5 market exit] ticker={V5_CONFIG.ticker}, volume={coin_amount:.12f}, response={response}")


def open_new_position() -> None:
    """완료된 5분봉 반등 신호가 있으면 V5 한도 안에서 시장가 매수를 요청합니다."""

    required_count = max(
        V5_CONFIG.strategy.rsi_period + 3,
        V5_CONFIG.strategy.bollinger_period + 2,
        V5_CONFIG.strategy.trend_sma_period + 1,
    )
    ohlcv = pyupbit.get_ohlcv(V5_CONFIG.ticker, interval=V5_CONFIG.interval, count=required_count)
    if ohlcv is None or len(ohlcv) < required_count:
        log("[V5 wait] 신호를 만들 OHLCV가 부족합니다.")
        return
    try:
        # API가 진행 중인 최신 봉을 포함할 수 있으므로, 미완료 봉은 신호에서 항상 제외합니다.
        signal = build_signal(ohlcv.iloc[:-1], V5_CONFIG.strategy)
    except ValueError as error:
        log(f"[V5 wait] signal creation failed: {error}")
        return
    krw_balance, _ = get_account_status()
    order_budget = calculate_order_budget(krw_balance, PORTFOLIO_CONFIG.v5_max_capital_krw)
    decision = decide_entry(signal, krw_balance, order_budget, V5_CONFIG.strategy)
    if decision.action == "WAIT":
        log(
            f"[V5 wait] RSI={signal.previous_rsi:.2f} → {signal.rsi:.2f}, "
            f"close={signal.price:,.0f}, lower band={signal.lower_band:,.0f}, "
            f"trend SMA={signal.trend_sma:,.0f}"
        )
        return
    response = UPBIT.buy_market_order(V5_CONFIG.ticker, decision.order_amount)
    if not isinstance(response, dict) or not response.get("uuid"):
        log(f"[V5 entry failed] response={response}")
        return
    save_trade_state(
        STATE_PATH,
        ScalpState(
            status="ENTRY_PENDING",
            entry_order_uuid=str(response["uuid"]),
            entry_cost_krw=decision.order_amount,
        ),
    )
    log(
        f"[V5 entry] ticker={V5_CONFIG.ticker}, amount={decision.order_amount:,.0f} KRW, "
        f"RSI={signal.previous_rsi:.2f} → {signal.rsi:.2f}, response={response}"
    )


def main() -> None:
    """저장된 V5 주문 상태를 우선 처리하고, 빈 포지션에서만 새 단타 진입을 판단합니다."""

    try:
        validate_v5_ticker(V5_CONFIG.ticker)
    except ValueError as error:
        log(f"[V5 safety] {error}")
        return
    state = load_trade_state(STATE_PATH)
    if state.status == "ENTRY_PENDING":
        handle_entry_pending(state)
        return
    if state.status == "TARGET_OPEN":
        handle_target_open(state)
        return
    if state.status == "EXIT_PENDING":
        handle_exit_pending(state)
        return
    if state.status != "FLAT":
        log(f"[V5 safety] 알 수 없는 상태({state.status})입니다. 수동으로 잔고를 확인하세요.")
        return

    _, coin_amount = get_account_status()
    current_price = pyupbit.get_current_price(V5_CONFIG.ticker)
    if current_price is not None and coin_amount * float(current_price) >= V5_CONFIG.strategy.trade.min_trade_krw:
        log("[V5 safety] 상태 파일 없는 V5 보유 물량이 있습니다. 자동 주문을 중단합니다.")
        return
    open_new_position()


if __name__ == "__main__":
    main()
