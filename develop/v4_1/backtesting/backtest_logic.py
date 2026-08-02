"""V4.1 추세 필터·손절 쿨다운 규칙을 과거 OHLCV에 적용하는 순수 백테스트입니다."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from develop.v3.backtesting.backtest_logic import (
    BacktestResult,
    BacktestTrade,
    build_strategy_ohlcv,
    calculate_period_source_count,
    calculate_source_count,
    select_source_interval,
    validate_ohlcv,
)
from develop.v4_1.config import V4_1_CONFIG, V4_1Config
from develop.v4_1.trade_logic import build_signal, decide_trade


def _infer_source_candle_duration(ohlcv: pd.DataFrame) -> pd.Timedelta:
    """원본 OHLCV 인덱스에서 한 캔들이 나타내는 최소 시간을 반환합니다.

    Args:
        ohlcv: 시간순 ``DatetimeIndex``를 가진 원본 OHLCV 데이터입니다.

    Returns:
        인접한 원본 캔들 시작 시각의 최소 간격입니다.

    Raises:
        ValueError: 인덱스가 증가하지 않거나 원본 캔들이 하나뿐일 때 발생합니다.
    """

    intervals = ohlcv.index.to_series().diff().dropna()
    if intervals.empty or (intervals <= pd.Timedelta(0)).any():
        raise ValueError("OHLCV index must contain increasing candle timestamps.")
    return pd.Timedelta(intervals.min())


def _is_scheduled_execution_time(timestamp: pd.Timestamp, cron_duration: pd.Timedelta) -> bool:
    """자정 기준 V4.1 크론 가정에 맞는 매매 판단 시점인지 반환합니다.

    Args:
        timestamp: 원본 봉이 끝나 V4.1이 판단할 수 있는 시각입니다.
        cron_duration: 백테스트에서 가정한 봇 실행 주기입니다.

    Returns:
        해당 시각이 자정 기준 크론 실행 시점이면 ``True``입니다.
    """

    elapsed_today = timestamp - timestamp.normalize()
    return elapsed_today % cron_duration == pd.Timedelta(0)


def run_backtest(
    ohlcv: pd.DataFrame,
    config: V4_1Config = V4_1_CONFIG,
    strategy_candle_anchor: pd.Timestamp | None = None,
    simulation_start: pd.Timestamp | None = None,
    simulation_end: pd.Timestamp | None = None,
) -> BacktestResult:
    """V4.1 규칙으로 크론 실행과 다음 원본 봉 시가 체결을 가정해 결과를 계산합니다.

    각 원본 봉이 끝날 때 그 시점까지의 부분 4시간 전략 봉으로 RSI와 추세 이동평균을 다시
    계산합니다. 크론 시점에는 V4.1의 순수 ``decide_trade``를 호출하고, 주문은 미래 정보를
    쓰지 않도록 다음 원본 봉 시가에 체결합니다. 손절이 체결된 시각은 이후 쿨다운 판단에
    저장합니다.

    Args:
        ohlcv: 크론 실행 주기보다 같거나 짧은 간격의 시간순 원본 OHLCV 데이터입니다.
        config: 티커·V4.1 전략·백테스트 체결 가정을 담은 전체 설정입니다.
        strategy_candle_anchor: 업비트가 현재 전략 봉을 시작한 실제 시각입니다.
        simulation_start: 시작 자금을 적용하고 그래프에 표시할 포함 시각입니다.
        simulation_end: 그래프에 표시할 배타적 종료 시각입니다.

    Returns:
        RSI·가격·자산 곡선, 체결 기록, 크론 판단 시각을 담은 백테스트 결과입니다.

    Raises:
        ValueError: OHLCV·설정·기간·전략 봉 기준 시각이 유효하지 않을 때 발생합니다.
    """

    validate_ohlcv(ohlcv, config)
    if strategy_candle_anchor is None:
        raise ValueError("strategy_candle_anchor is required for backtesting.")
    if simulation_start is not None:
        simulation_start = pd.Timestamp(simulation_start)
    if simulation_end is not None:
        simulation_end = pd.Timestamp(simulation_end)
    if simulation_start is not None and simulation_end is not None and simulation_end <= simulation_start:
        raise ValueError("simulation_end must be later than simulation_start.")

    prices = ohlcv.copy()
    source_candle_duration = _infer_source_candle_duration(prices)
    event_times = prices.index + source_candle_duration
    close_prices = pd.Series(prices["close"].to_numpy(), index=event_times, name="close")
    rsi = pd.Series(index=event_times, dtype=float, name="RSI")
    cash = config.backtest.initial_capital
    coin_amount = 0.0
    average_buy_price = 0.0
    last_stop_loss_time: datetime | None = None
    trades: list[BacktestTrade] = []
    equity_values: list[float] = []
    evaluation_times: list[pd.Timestamp] = []
    cron_duration = pd.Timedelta(minutes=config.backtest.cron_interval_minutes)

    for position, (source_candle_start, candle) in enumerate(prices.iterrows()):
        signal_time = source_candle_start + source_candle_duration
        current_price = float(candle["close"])
        equity_values.append(cash + coin_amount * current_price)

        strategy_ohlcv = build_strategy_ohlcv(
            prices.iloc[: position + 1],
            config.interval,
            strategy_candle_anchor,
        )
        try:
            signal = build_signal(strategy_ohlcv, config.strategy)
        except ValueError:
            continue
        rsi.iloc[position] = signal.rsi

        if position >= len(prices) - 1:
            continue
        if simulation_start is not None and signal_time < simulation_start:
            continue
        if simulation_end is not None and signal_time >= simulation_end:
            continue
        if not _is_scheduled_execution_time(signal_time, cron_duration):
            continue

        evaluation_times.append(signal_time)
        decision = decide_trade(
            signal,
            cash,
            coin_amount,
            average_buy_price,
            signal_time.to_pydatetime(),
            last_stop_loss_time,
            config.strategy.trade,
        )
        if decision.action == "WAIT":
            continue

        execution_price = float(prices.iloc[position + 1]["open"])
        if execution_price <= 0:
            continue
        execution_time = signal_time + source_candle_duration

        if decision.action == "BUY":
            order_amount = min(decision.order_amount, cash)
            bought_amount = order_amount * (1 - config.backtest.fee_rate) / execution_price
            if bought_amount <= 0:
                continue
            total_cost = average_buy_price * coin_amount + order_amount
            cash -= order_amount
            coin_amount += bought_amount
            average_buy_price = total_cost / coin_amount
        else:
            order_amount = min(decision.order_amount, coin_amount)
            if order_amount <= 0:
                continue
            cash += order_amount * execution_price * (1 - config.backtest.fee_rate)
            coin_amount -= order_amount
            if coin_amount <= 0:
                coin_amount = 0.0
                average_buy_price = 0.0
            if decision.action == "SELL_STOP_LOSS":
                last_stop_loss_time = execution_time.to_pydatetime()

        trades.append(
            BacktestTrade(
                action=decision.action,
                signal_time=signal_time,
                execution_time=execution_time,
                execution_price=execution_price,
                order_amount=order_amount,
                profit_rate=decision.profit_rate,
            )
        )

    visible_mask = pd.Series(True, index=event_times)
    if simulation_start is not None:
        visible_mask &= event_times >= simulation_start
    if simulation_end is not None:
        visible_mask &= event_times < simulation_end
    if not visible_mask.any():
        raise ValueError("No completed source candles exist in the requested simulation period.")

    close_prices = close_prices.loc[visible_mask]
    rsi = rsi.loc[visible_mask]
    equity_curve = pd.Series(equity_values, index=event_times, name="equity").loc[visible_mask]
    final_equity = float(equity_curve.iloc[-1])
    total_return_pct = (final_equity / config.backtest.initial_capital - 1) * 100
    return BacktestResult(
        initial_capital=config.backtest.initial_capital,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        close_prices=close_prices,
        rsi=rsi,
        equity_curve=equity_curve,
        trades=trades,
        evaluation_times=evaluation_times,
    )
