from __future__ import annotations

# ==========================
# V1 전략 알고리즘
# ==========================
# 대상 코인 선정
# get_top_coin_list("day", top=10)으로 최근 거래대금 상위 10개만 봅니다.
# 이렇게 하면 거래량 부족한 알트는 초반에 제외할 수 있어요.
#
# 매수 조건
# 일봉 기준 MA5 > MA20 이고 현재가가 MA5 위에 있는 코인만 후보로 둡니다.
# 그 다음 minute60 기준 RSI가 이전 봉 35 이하 -> 현재 봉 35 초과로 올라올 때 진입합니다.
# 즉, "상승 추세 안에서 눌림 후 반등"만 노리는 구조예요.
#
# 매수 방식
# 동시 보유는 최대 3종목.
# 총 자산의 20~25%씩 분할 진입.
# 이미 보유 중이면 추가 매수는 금지해서 v1을 단순하게 유지합니다.
#
# 매도 조건
# 손절: 수익률 -3%
# 익절: 수익률 +5%
# 추세 이탈: minute60 기준 MA5 < MA20
# 과열 차익실현: RSI 70 이상에서 꺾이면 매도
# 이 4개 중 하나라도 충족하면 시장가 매도합니다.

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.upbit_develop_library import (  # noqa: E402
    get_has_coin_count,
    get_moving_average,
    get_ohlcv,
    get_revenue_rate,
    get_rsi,
    get_top_coin_list,
    has_coin,
)


@dataclass(frozen=True)
class StrategyConfig:
    """V1 전략에서 사용하는 기준값들을 모아둔 설정 객체."""

    # 조회할 마켓 구분값입니다. 기본은 원화마켓입니다.
    market: str = "KRW"
    # 거래대금 기준으로 상위 몇 개 코인을 스캔할지 정합니다.
    top_n: int = 10
    # 동시에 들고 갈 최대 보유 종목 수입니다.
    max_holdings: int = 3
    # 현재 원화 잔고 중 한 번 진입에 사용할 비율입니다.
    allocation_ratio: float = 0.25
    # 업비트 최소 주문 금액을 고려한 최소 매수 금액입니다.
    min_trade_krw: float = 5000.0
    # 거래대금 상위 코인을 고를 때 사용할 추세 기준 캔들 간격입니다.
    trend_interval: str = "day"
    # 실제 진입/청산 타이밍을 볼 때 사용할 신호용 캔들 간격입니다.
    signal_interval: str = "minute60"
    # 일봉 추세 판단에 가져올 캔들 개수입니다.
    trend_count: int = 30
    # RSI와 시간봉 이평 계산에 가져올 캔들 개수입니다.
    signal_count: int = 50
    # RSI 계산 기간입니다.
    rsi_period: int = 14
    # 이전 봉 이하였다가 현재 봉에서 돌파해야 하는 매수 RSI 기준선입니다.
    entry_rsi_threshold: float = 35.0
    # 과열 구간 판단에 사용하는 RSI 기준선입니다.
    exit_rsi_threshold: float = 70.0
    # 이 수익률 이하로 내려가면 손절하는 기준입니다.
    stop_loss_pct: float = -3.0
    # 이 수익률 이상이 되면 익절하는 기준입니다.
    take_profit_pct: float = 5.0
    # 단기 추세 확인용 이동평균 기간입니다.
    short_ma_period: int = 5
    # 중기 추세 확인용 이동평균 기간입니다.
    long_ma_period: int = 20


@dataclass(frozen=True)
class EntrySignal:
    """매수 후보 판단 결과를 담는 데이터 객체."""

    ticker: str
    should_buy: bool
    reason: str
    day_ma_short: float
    day_ma_long: float
    day_close: float
    rsi_prev: float
    rsi_now: float


@dataclass(frozen=True)
class ExitSignal:
    """매도 여부 판단 결과를 담는 데이터 객체."""

    ticker: str
    should_sell: bool
    reason: str
    revenue_rate: float
    signal_ma_short: float
    signal_ma_long: float
    rsi_prev: float
    rsi_now: float


def _has_required_rows(day_df: Any, signal_df: Any, config: StrategyConfig) -> bool:
    """이평선과 RSI 계산에 필요한 최소 캔들 수가 있는지 확인합니다."""

    return (
        day_df is not None
        and signal_df is not None
        and len(day_df) >= config.long_ma_period
        and len(signal_df) >= max(config.long_ma_period, config.rsi_period + 1)
    )


def evaluate_entry_signal(
    ticker: str,
    day_df: Any,
    signal_df: Any,
    config: StrategyConfig = StrategyConfig(),
) -> EntrySignal:
    """추세와 RSI 반등 조건을 함께 확인해 매수 신호를 계산합니다."""

    if not _has_required_rows(day_df, signal_df, config):
        return EntrySignal(ticker, False, "not_enough_data", 0.0, 0.0, 0.0, 0.0, 0.0)

    day_ma_short = get_moving_average(day_df, config.short_ma_period, -1)
    day_ma_long = get_moving_average(day_df, config.long_ma_period, -1)
    day_close = float(day_df["close"].iloc[-1])
    rsi_prev = get_rsi(signal_df, config.rsi_period, -2)
    rsi_now = get_rsi(signal_df, config.rsi_period, -1)

    if day_ma_short <= day_ma_long:
        return EntrySignal(
            ticker,
            False,
            "trend_not_bullish",
            day_ma_short,
            day_ma_long,
            day_close,
            rsi_prev,
            rsi_now,
        )

    if day_close <= day_ma_short:
        return EntrySignal(
            ticker,
            False,
            "close_below_short_ma",
            day_ma_short,
            day_ma_long,
            day_close,
            rsi_prev,
            rsi_now,
        )

    if not (rsi_prev <= config.entry_rsi_threshold < rsi_now):
        return EntrySignal(
            ticker,
            False,
            "rsi_entry_not_triggered",
            day_ma_short,
            day_ma_long,
            day_close,
            rsi_prev,
            rsi_now,
        )

    return EntrySignal(
        ticker,
        True,
        "buy_signal",
        day_ma_short,
        day_ma_long,
        day_close,
        rsi_prev,
        rsi_now,
    )


def evaluate_exit_signal(
    ticker: str,
    balances: list[dict[str, Any]] | dict[str, dict[str, Any]],
    signal_df: Any,
    config: StrategyConfig = StrategyConfig(),
) -> ExitSignal:
    """손절, 익절, 추세 이탈, 과열 꺾임 조건으로 매도 신호를 계산합니다."""

    if signal_df is None or len(signal_df) < max(config.long_ma_period, config.rsi_period + 1):
        return ExitSignal(ticker, False, "not_enough_data", 0.0, 0.0, 0.0, 0.0, 0.0)

    revenue_rate = get_revenue_rate(balances, ticker, sleep_seconds=0.0)
    signal_ma_short = get_moving_average(signal_df, config.short_ma_period, -1)
    signal_ma_long = get_moving_average(signal_df, config.long_ma_period, -1)
    rsi_prev = get_rsi(signal_df, config.rsi_period, -2)
    rsi_now = get_rsi(signal_df, config.rsi_period, -1)

    if revenue_rate <= config.stop_loss_pct:
        return ExitSignal(
            ticker,
            True,
            "stop_loss",
            revenue_rate,
            signal_ma_short,
            signal_ma_long,
            rsi_prev,
            rsi_now,
        )

    if revenue_rate >= config.take_profit_pct:
        return ExitSignal(
            ticker,
            True,
            "take_profit",
            revenue_rate,
            signal_ma_short,
            signal_ma_long,
            rsi_prev,
            rsi_now,
        )

    if signal_ma_short < signal_ma_long:
        return ExitSignal(
            ticker,
            True,
            "trend_breakdown",
            revenue_rate,
            signal_ma_short,
            signal_ma_long,
            rsi_prev,
            rsi_now,
        )

    if rsi_prev >= config.exit_rsi_threshold and rsi_now < rsi_prev:
        return ExitSignal(
            ticker,
            True,
            "rsi_pullback_after_overbought",
            revenue_rate,
            signal_ma_short,
            signal_ma_long,
            rsi_prev,
            rsi_now,
        )

    return ExitSignal(
        ticker,
        False,
        "hold",
        revenue_rate,
        signal_ma_short,
        signal_ma_long,
        rsi_prev,
        rsi_now,
    )


def calculate_order_budget(
    krw_balance: float,
    config: StrategyConfig = StrategyConfig(),
) -> float:
    """현재 원화 잔고에서 이번 진입에 사용할 주문 가능 금액을 계산합니다."""

    budget = krw_balance * config.allocation_ratio
    if budget < config.min_trade_krw:
        return 0.0
    return budget


def build_v1_signals(
    balances: list[dict[str, Any]],
    krw_balance: float,
    config: StrategyConfig = StrategyConfig(),
) -> dict[str, Any]:
    """상위 거래대금 코인을 순회하며 전체 매수/매도 후보를 모읍니다."""

    top_tickers = get_top_coin_list(config.trend_interval, config.top_n, market=config.market)
    buy_signals: list[EntrySignal] = []
    sell_signals: list[ExitSignal] = []

    holding_count = get_has_coin_count(balances)
    can_add_position = holding_count < config.max_holdings
    order_budget = calculate_order_budget(krw_balance, config)

    for ticker in top_tickers:
        signal_df = get_ohlcv(ticker, interval=config.signal_interval, count=config.signal_count)

        if has_coin(balances, ticker):
            sell_signals.append(evaluate_exit_signal(ticker, balances, signal_df, config))
            continue

        if not can_add_position or order_budget == 0.0:
            continue

        day_df = get_ohlcv(ticker, interval=config.trend_interval, count=config.trend_count)
        entry_signal = evaluate_entry_signal(ticker, day_df, signal_df, config)
        if entry_signal.should_buy:
            buy_signals.append(entry_signal)

    return {
        "config": config,
        "top_tickers": top_tickers,
        "order_budget": order_budget,
        "holding_count": holding_count,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
    }


def summarize_signals(result: dict[str, Any]) -> str:
    """계산된 신호들을 사람이 읽기 쉬운 텍스트로 요약합니다."""

    lines = [
        "[V1 Strategy Summary]",
        f"- scan_tickers: {len(result['top_tickers'])}",
        f"- current_holdings: {result['holding_count']}",
        f"- order_budget: {result['order_budget']:.0f} KRW",
    ]

    buy_signals: list[EntrySignal] = result["buy_signals"]
    sell_signals: list[ExitSignal] = result["sell_signals"]

    if buy_signals:
        lines.append("- buy_candidates:")
        for signal in buy_signals:
            lines.append(
                "  "
                f"{signal.ticker} | RSI {signal.rsi_prev:.2f}->{signal.rsi_now:.2f} | "
                f"MA{result['config'].short_ma_period} {signal.day_ma_short:.0f} > "
                f"MA{result['config'].long_ma_period} {signal.day_ma_long:.0f}"
            )
    else:
        lines.append("- buy_candidates: none")

    if sell_signals:
        lines.append("- sell_checks:")
        for signal in sell_signals:
            lines.append(
                "  "
                f"{signal.ticker} | action={'SELL' if signal.should_sell else 'HOLD'} | "
                f"reason={signal.reason} | revenue={signal.revenue_rate:.2f}%"
            )
    else:
        lines.append("- sell_checks: none")

    return "\n".join(lines)


def main() -> None:
    """단독 실행 시 이 모듈의 역할을 간단히 안내합니다."""

    print(
        "This module builds V1 strategy signals only. "
        "Wire balances and KRW balance from your account code before live trading."
    )


if __name__ == "__main__":
    main()
