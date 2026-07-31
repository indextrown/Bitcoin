from __future__ import annotations

# ==========================
# V0 전략 알고리즘
# ==========================
# 대상 코인 선정
# V0는 상위 거래대금 코인을 고르지 않고, 미리 정한 단일 코인 1개만 봅니다.
# 기본값은 KRW-ETH이고 4시간봉 RSI만으로 단순하게 판단합니다.
#
# 매수 조건
# minute240 기준 RSI가 30 이하로 내려오면 과매도 구간으로 보고 진입합니다.
# 한 번에 남은 원화의 20%만 시장가로 매수합니다.
#
# 매수 방식
# 분할 매수 비율은 20%입니다.
# 최소 주문 금액 5,000원 이상일 때만 진입합니다.
# 별도 종목 분산 없이 한 종목만 반복해서 봅니다.
#
# 매도 조건
# RSI가 70 이상일 때만 매도 조건 검사를 시작합니다.
# 그 상태에서 수익률이 0% 이하이면 본전 또는 손실 정리로 전량 매도합니다.
# 또는 수익률이 +5% 이상이면 익절로 전량 매도합니다.

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.upbit_develop_library import (  # noqa: E402
    get_ohlcv,
    get_revenue_rate,
    get_rsi,
    has_coin,
)


@dataclass(frozen=True)
class StrategyConfig:
    """V0 RSI 단일 코인 전략의 기준값 설정입니다."""

    # 관찰할 단일 티커입니다.
    ticker: str = "KRW-ETH"
    # 신호를 확인할 캔들 간격입니다.
    interval: str = "minute240"
    # RSI 계산에 사용할 캔들 개수입니다.
    count: int = 60
    # RSI 계산 기간입니다.
    rsi_period: int = 14
    # 이 값 이하이면 과매도로 보고 매수합니다.
    buy_threshold: float = 30.0
    # 이 값 이상이면 매도 조건 검사를 시작합니다.
    sell_threshold: float = 70.0
    # 현재 원화 잔고에서 한 번 매수할 비율입니다.
    buy_ratio: float = 0.2
    # 최소 주문 금액입니다.
    min_trade_krw: float = 5000.0
    # 이 수익률 이상이면 익절합니다.
    take_profit_pct: float = 5.0
    # 이 수익률 이하이면 본전 또는 손실 정리로 매도합니다.
    flat_or_loss_pct: float = 0.0


@dataclass(frozen=True)
class SignalSnapshot:
    """현재 캔들 기준의 RSI와 가격 상태를 담습니다."""

    ticker: str
    price: float
    rsi_now: float
    rsi_prev: float


@dataclass(frozen=True)
class EntrySignal:
    """매수 여부와 이유를 담는 결과 객체입니다."""

    should_buy: bool
    reason: str
    order_budget: float
    snapshot: SignalSnapshot


@dataclass(frozen=True)
class ExitSignal:
    """매도 여부와 이유를 담는 결과 객체입니다."""

    should_sell: bool
    reason: str
    revenue_rate: float
    snapshot: SignalSnapshot


def build_snapshot(
    ticker: str,
    df: Any,
    config: StrategyConfig = StrategyConfig(),
) -> SignalSnapshot:
    """OHLCV에서 현재 가격과 직전/현재 RSI를 추출합니다."""

    return SignalSnapshot(
        ticker=ticker,
        price=float(df["close"].iloc[-1]),
        rsi_now=get_rsi(df, config.rsi_period, -1),
        rsi_prev=get_rsi(df, config.rsi_period, -2),
    )


def calculate_order_budget(
    krw_balance: float,
    config: StrategyConfig = StrategyConfig(),
) -> float:
    """남은 원화에서 V0 분할 매수 금액을 계산합니다."""

    budget = krw_balance * config.buy_ratio
    if budget < config.min_trade_krw:
        return 0.0
    return budget


def evaluate_entry_signal(
    snapshot: SignalSnapshot,
    krw_balance: float,
    already_holding: bool,
    config: StrategyConfig = StrategyConfig(),
) -> EntrySignal:
    """RSI 과매도 구간과 주문 가능 금액을 기준으로 매수 여부를 판단합니다."""

    order_budget = calculate_order_budget(krw_balance, config)

    if already_holding:
        return EntrySignal(False, "already_holding", 0.0, snapshot)

    if order_budget == 0.0:
        return EntrySignal(False, "insufficient_krw", 0.0, snapshot)

    if snapshot.rsi_now > config.buy_threshold:
        return EntrySignal(False, "rsi_not_low_enough", order_budget, snapshot)

    return EntrySignal(True, "buy_signal", order_budget, snapshot)


def evaluate_exit_signal(
    snapshot: SignalSnapshot,
    balances: list[dict[str, Any]] | dict[str, dict[str, Any]],
    config: StrategyConfig = StrategyConfig(),
) -> ExitSignal:
    """RSI 과열 구간에서 손익 기준으로 매도 여부를 판단합니다."""

    revenue_rate = get_revenue_rate(balances, snapshot.ticker, sleep_seconds=0.0)

    if snapshot.rsi_now < config.sell_threshold:
        return ExitSignal(False, "rsi_not_high_enough", revenue_rate, snapshot)

    if revenue_rate <= config.flat_or_loss_pct:
        return ExitSignal(True, "flat_or_loss_exit", revenue_rate, snapshot)

    if revenue_rate >= config.take_profit_pct:
        return ExitSignal(True, "take_profit", revenue_rate, snapshot)

    return ExitSignal(False, "hold", revenue_rate, snapshot)


def build_v0_signal(
    balances: list[dict[str, Any]],
    krw_balance: float,
    config: StrategyConfig = StrategyConfig(),
) -> dict[str, Any]:
    """단일 코인 기준으로 현재 매수/매도 신호를 계산합니다."""

    df = get_ohlcv(config.ticker, interval=config.interval, count=config.count)
    snapshot = build_snapshot(config.ticker, df, config)
    holding = has_coin(balances, config.ticker)

    entry_signal = evaluate_entry_signal(snapshot, krw_balance, holding, config)
    exit_signal = None
    if holding:
        exit_signal = evaluate_exit_signal(snapshot, balances, config)

    return {
        "config": config,
        "snapshot": snapshot,
        "holding": holding,
        "entry_signal": entry_signal,
        "exit_signal": exit_signal,
    }


def summarize_signal(result: dict[str, Any]) -> str:
    """V0 전략 계산 결과를 텍스트로 간단히 요약합니다."""

    snapshot: SignalSnapshot = result["snapshot"]
    entry_signal: EntrySignal = result["entry_signal"]
    exit_signal: ExitSignal | None = result["exit_signal"]

    lines = [
        "[V0 Strategy Summary]",
        f"- ticker: {snapshot.ticker}",
        f"- price: {snapshot.price:.0f} KRW",
        f"- RSI: {snapshot.rsi_prev:.2f} -> {snapshot.rsi_now:.2f}",
        f"- holding: {'yes' if result['holding'] else 'no'}",
        f"- entry: {'BUY' if entry_signal.should_buy else 'WAIT'} ({entry_signal.reason})",
        f"- order_budget: {entry_signal.order_budget:.0f} KRW",
    ]

    if exit_signal is not None:
        lines.append(
            f"- exit: {'SELL' if exit_signal.should_sell else 'HOLD'} "
            f"({exit_signal.reason}, revenue={exit_signal.revenue_rate:.2f}%)"
        )

    return "\n".join(lines)


def main() -> None:
    """단독 실행 시 이 모듈의 역할만 안내합니다."""

    print(
        "This module builds V0 strategy signals only. "
        "Wire balances and KRW balance from your account code before live trading."
    )


if __name__ == "__main__":
    main()
