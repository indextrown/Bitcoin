from __future__ import annotations

# ==========================
# V2 전략 알고리즘
# ==========================
# 대상 코인 선정
# get_top_coin_list("day", top=15)로 최근 거래대금 상위 코인만 추립니다.
# 실거래에서 유동성이 충분한 종목 위주로만 스캔해 슬리피지 리스크를 줄입니다.
#
# 매수 조건
# 일봉 기준 EMA20 > EMA50 이고 현재가가 EMA20 위에 있어야 합니다.
# 4시간봉 기준 최근 20봉 최고가를 종가로 돌파해야 합니다.
# 동시에 거래량이 최근 평균 대비 급증하고 RSI가 55 이상이어야 진입합니다.
# 즉, "상승 추세 안에서 강한 돌파가 실제 자금 유입과 함께 나오는지"를 봅니다.
#
# 매수 방식
# 최대 보유 4종목.
# 기본은 원화 잔고의 20%를 상한으로 두고,
# ATR 변동성에 따라 실제 주문 금액을 더 줄이는 리스크 기반 포지션 사이징을 적용합니다.
#
# 매도 조건
# 손절: 수익률 -4%
# 추세 이탈: 4시간봉 EMA10 < EMA20
# 브레이크아웃 실패: 진입 후 종가가 10봉 저점 아래로 밀림
# 과열 후 꺾임: RSI 75 이상이었던 흐름에서 RSI가 하락 반전

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.upbit_develop_library import (  # noqa: E402
    get_atr,
    get_exponential_moving_average,
    get_has_coin_count,
    get_ohlcv,
    get_revenue_rate,
    get_rsi,
    get_top_coin_list,
    has_coin,
)


@dataclass(frozen=True)
class StrategyConfig:
    """V2 추세추종 브레이크아웃 전략 설정값입니다."""

    market: str = "KRW"
    top_n: int = 15
    max_holdings: int = 4
    allocation_ratio: float = 0.2
    risk_per_trade_ratio: float = 0.02
    min_trade_krw: float = 5000.0
    trend_interval: str = "day"
    signal_interval: str = "minute240"
    trend_count: int = 80
    signal_count: int = 80
    fast_ema_period: int = 20
    slow_ema_period: int = 50
    signal_fast_ema_period: int = 10
    signal_slow_ema_period: int = 20
    breakout_lookback: int = 20
    breakdown_lookback: int = 10
    volume_ma_period: int = 20
    volume_surge_multiplier: float = 1.3
    rsi_period: int = 14
    entry_rsi_threshold: float = 55.0
    exit_rsi_threshold: float = 75.0
    atr_period: int = 14
    atr_stop_multiple: float = 2.0
    stop_loss_pct: float = -4.0


@dataclass(frozen=True)
class EntrySignal:
    """매수 후보 판단 결과입니다."""

    ticker: str
    should_buy: bool
    reason: str
    trend_ema_fast: float
    trend_ema_slow: float
    signal_ema_fast: float
    signal_ema_slow: float
    breakout_level: float
    close_price: float
    volume_ratio: float
    rsi_now: float
    atr: float


@dataclass(frozen=True)
class ExitSignal:
    """매도 여부 판단 결과입니다."""

    ticker: str
    should_sell: bool
    reason: str
    revenue_rate: float
    signal_ema_fast: float
    signal_ema_slow: float
    breakdown_level: float
    close_price: float
    rsi_prev: float
    rsi_now: float


def _has_required_rows(day_df: Any, signal_df: Any, config: StrategyConfig) -> bool:
    """EMA, ATR, 브레이크아웃 계산에 필요한 최소 캔들 수를 확인합니다."""

    min_signal_rows = max(
        config.signal_slow_ema_period,
        config.breakout_lookback + 1,
        config.breakdown_lookback + 1,
        config.volume_ma_period,
        config.atr_period,
        config.rsi_period + 1,
    )
    return (
        day_df is not None
        and signal_df is not None
        and len(day_df) >= config.slow_ema_period
        and len(signal_df) >= min_signal_rows
    )


def _get_breakout_level(signal_df: Any, lookback: int) -> float:
    """현재 봉을 제외한 직전 lookback 봉의 최고가를 반환합니다."""

    return float(signal_df["high"].iloc[-(lookback + 1) : -1].max())


def _get_breakdown_level(signal_df: Any, lookback: int) -> float:
    """현재 봉을 제외한 직전 lookback 봉의 최저가를 반환합니다."""

    return float(signal_df["low"].iloc[-(lookback + 1) : -1].min())


def _get_volume_ratio(signal_df: Any, period: int) -> float:
    """현재 거래량이 최근 평균 대비 몇 배인지 계산합니다."""

    volume_now = float(signal_df["volume"].iloc[-1])
    volume_avg = float(signal_df["volume"].rolling(period).mean().iloc[-2])
    if volume_avg == 0:
        return 0.0
    return volume_now / volume_avg


def calculate_order_budget(
    krw_balance: float,
    signal_df: Any,
    config: StrategyConfig = StrategyConfig(),
) -> float:
    """잔고 상한과 ATR 리스크를 함께 고려한 주문 가능 금액을 계산합니다."""

    max_budget = krw_balance * config.allocation_ratio
    if signal_df is None or len(signal_df) < config.atr_period:
        return 0.0

    close_price = float(signal_df["close"].iloc[-1])
    atr = get_atr(signal_df, config.atr_period, -1)
    atr_risk_ratio = (atr * config.atr_stop_multiple) / close_price if close_price else 0.0

    if atr_risk_ratio <= 0:
        return 0.0

    risk_budget = krw_balance * config.risk_per_trade_ratio / atr_risk_ratio
    budget = min(max_budget, risk_budget)

    if budget < config.min_trade_krw:
        return 0.0
    return budget


def evaluate_entry_signal(
    ticker: str,
    day_df: Any,
    signal_df: Any,
    config: StrategyConfig = StrategyConfig(),
) -> EntrySignal:
    """추세 필터와 브레이크아웃 조건을 함께 확인해 매수 신호를 계산합니다."""

    if not _has_required_rows(day_df, signal_df, config):
        return EntrySignal(
            ticker, False, "not_enough_data", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        )

    trend_ema_fast = get_exponential_moving_average(day_df, config.fast_ema_period, -1)
    trend_ema_slow = get_exponential_moving_average(day_df, config.slow_ema_period, -1)
    signal_ema_fast = get_exponential_moving_average(signal_df, config.signal_fast_ema_period, -1)
    signal_ema_slow = get_exponential_moving_average(signal_df, config.signal_slow_ema_period, -1)
    breakout_level = _get_breakout_level(signal_df, config.breakout_lookback)
    close_price = float(signal_df["close"].iloc[-1])
    volume_ratio = _get_volume_ratio(signal_df, config.volume_ma_period)
    rsi_now = get_rsi(signal_df, config.rsi_period, -1)
    atr = get_atr(signal_df, config.atr_period, -1)

    if trend_ema_fast <= trend_ema_slow:
        return EntrySignal(
            ticker,
            False,
            "trend_not_bullish",
            trend_ema_fast,
            trend_ema_slow,
            signal_ema_fast,
            signal_ema_slow,
            breakout_level,
            close_price,
            volume_ratio,
            rsi_now,
            atr,
        )

    if float(day_df["close"].iloc[-1]) <= trend_ema_fast:
        return EntrySignal(
            ticker,
            False,
            "close_below_trend_ema",
            trend_ema_fast,
            trend_ema_slow,
            signal_ema_fast,
            signal_ema_slow,
            breakout_level,
            close_price,
            volume_ratio,
            rsi_now,
            atr,
        )

    if signal_ema_fast <= signal_ema_slow:
        return EntrySignal(
            ticker,
            False,
            "signal_trend_not_aligned",
            trend_ema_fast,
            trend_ema_slow,
            signal_ema_fast,
            signal_ema_slow,
            breakout_level,
            close_price,
            volume_ratio,
            rsi_now,
            atr,
        )

    if close_price <= breakout_level:
        return EntrySignal(
            ticker,
            False,
            "breakout_not_triggered",
            trend_ema_fast,
            trend_ema_slow,
            signal_ema_fast,
            signal_ema_slow,
            breakout_level,
            close_price,
            volume_ratio,
            rsi_now,
            atr,
        )

    if volume_ratio < config.volume_surge_multiplier:
        return EntrySignal(
            ticker,
            False,
            "volume_not_confirmed",
            trend_ema_fast,
            trend_ema_slow,
            signal_ema_fast,
            signal_ema_slow,
            breakout_level,
            close_price,
            volume_ratio,
            rsi_now,
            atr,
        )

    if rsi_now < config.entry_rsi_threshold:
        return EntrySignal(
            ticker,
            False,
            "momentum_not_strong_enough",
            trend_ema_fast,
            trend_ema_slow,
            signal_ema_fast,
            signal_ema_slow,
            breakout_level,
            close_price,
            volume_ratio,
            rsi_now,
            atr,
        )

    return EntrySignal(
        ticker,
        True,
        "buy_signal",
        trend_ema_fast,
        trend_ema_slow,
        signal_ema_fast,
        signal_ema_slow,
        breakout_level,
        close_price,
        volume_ratio,
        rsi_now,
        atr,
    )


def evaluate_exit_signal(
    ticker: str,
    balances: list[dict[str, Any]] | dict[str, dict[str, Any]],
    signal_df: Any,
    config: StrategyConfig = StrategyConfig(),
) -> ExitSignal:
    """손절, 추세 이탈, 브레이크다운, 과열 반전 조건으로 매도 신호를 계산합니다."""

    min_signal_rows = max(
        config.signal_slow_ema_period,
        config.breakdown_lookback + 1,
        config.rsi_period + 1,
    )
    if signal_df is None or len(signal_df) < min_signal_rows:
        return ExitSignal(ticker, False, "not_enough_data", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    revenue_rate = get_revenue_rate(balances, ticker, sleep_seconds=0.0)
    signal_ema_fast = get_exponential_moving_average(signal_df, config.signal_fast_ema_period, -1)
    signal_ema_slow = get_exponential_moving_average(signal_df, config.signal_slow_ema_period, -1)
    breakdown_level = _get_breakdown_level(signal_df, config.breakdown_lookback)
    close_price = float(signal_df["close"].iloc[-1])
    rsi_prev = get_rsi(signal_df, config.rsi_period, -2)
    rsi_now = get_rsi(signal_df, config.rsi_period, -1)

    if revenue_rate <= config.stop_loss_pct:
        return ExitSignal(
            ticker,
            True,
            "stop_loss",
            revenue_rate,
            signal_ema_fast,
            signal_ema_slow,
            breakdown_level,
            close_price,
            rsi_prev,
            rsi_now,
        )

    if signal_ema_fast < signal_ema_slow:
        return ExitSignal(
            ticker,
            True,
            "trend_breakdown",
            revenue_rate,
            signal_ema_fast,
            signal_ema_slow,
            breakdown_level,
            close_price,
            rsi_prev,
            rsi_now,
        )

    if close_price < breakdown_level:
        return ExitSignal(
            ticker,
            True,
            "breakout_failure",
            revenue_rate,
            signal_ema_fast,
            signal_ema_slow,
            breakdown_level,
            close_price,
            rsi_prev,
            rsi_now,
        )

    if rsi_prev >= config.exit_rsi_threshold and rsi_now < rsi_prev:
        return ExitSignal(
            ticker,
            True,
            "momentum_fade_after_overbought",
            revenue_rate,
            signal_ema_fast,
            signal_ema_slow,
            breakdown_level,
            close_price,
            rsi_prev,
            rsi_now,
        )

    return ExitSignal(
        ticker,
        False,
        "hold",
        revenue_rate,
        signal_ema_fast,
        signal_ema_slow,
        breakdown_level,
        close_price,
        rsi_prev,
        rsi_now,
    )


def build_v2_signals(
    balances: list[dict[str, Any]],
    krw_balance: float,
    config: StrategyConfig = StrategyConfig(),
) -> dict[str, Any]:
    """상위 거래대금 코인을 순회하며 V2 매수/매도 후보를 모읍니다."""

    top_tickers = get_top_coin_list(config.trend_interval, config.top_n, market=config.market)
    buy_signals: list[EntrySignal] = []
    sell_signals: list[ExitSignal] = []

    holding_count = get_has_coin_count(balances)
    can_add_position = holding_count < config.max_holdings

    for ticker in top_tickers:
        signal_df = get_ohlcv(ticker, interval=config.signal_interval, count=config.signal_count)

        if has_coin(balances, ticker):
            sell_signals.append(evaluate_exit_signal(ticker, balances, signal_df, config))
            continue

        if not can_add_position:
            continue

        order_budget = calculate_order_budget(krw_balance, signal_df, config)
        if order_budget == 0.0:
            continue

        day_df = get_ohlcv(ticker, interval=config.trend_interval, count=config.trend_count)
        entry_signal = evaluate_entry_signal(ticker, day_df, signal_df, config)
        if entry_signal.should_buy:
            buy_signals.append(entry_signal)

    return {
        "config": config,
        "top_tickers": top_tickers,
        "holding_count": holding_count,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
    }


def summarize_signals(result: dict[str, Any]) -> str:
    """계산된 V2 신호를 사람이 읽기 쉬운 텍스트로 요약합니다."""

    lines = [
        "[V2 Strategy Summary]",
        f"- top_tickers: {', '.join(result['top_tickers']) if result['top_tickers'] else '(none)'}",
        f"- holding_count: {result['holding_count']}",
        f"- buy_signals: {len(result['buy_signals'])}",
        f"- sell_signals: {len(result['sell_signals'])}",
    ]

    for signal in result["buy_signals"]:
        lines.append(
            f"- BUY {signal.ticker}: {signal.reason}, "
            f"close={signal.close_price:.0f}, breakout={signal.breakout_level:.0f}, "
            f"volume_ratio={signal.volume_ratio:.2f}, rsi={signal.rsi_now:.2f}"
        )

    for signal in result["sell_signals"]:
        lines.append(
            f"- SELL {signal.ticker}: {signal.reason}, "
            f"close={signal.close_price:.0f}, breakdown={signal.breakdown_level:.0f}, "
            f"revenue={signal.revenue_rate:.2f}%"
        )

    return "\n".join(lines)


def main() -> None:
    """단독 실행 시 이 모듈의 역할만 안내합니다."""

    print(
        "This module builds V2 breakout strategy signals only. "
        "Wire balances and KRW balance from your account code before live trading."
    )


if __name__ == "__main__":
    main()
