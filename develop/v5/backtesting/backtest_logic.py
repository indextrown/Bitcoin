"""V5 단타 규칙을 5분 OHLCV에 적용하는 순수 백테스트입니다."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from develop.v3.backtesting.backtest_logic import BacktestResult, BacktestTrade
from develop.v5.config import V5_CONFIG, V5Config, interval_to_timedelta
from develop.v5.trade_logic import (
    SignalSnapshot,
    calculate_signal_frame,
    calculate_target_price,
    decide_entry,
    decide_exit,
)


@dataclass(frozen=True)
class PendingEntry:
    """신호 다음 원본 봉 시가에 체결할 V5 시장가 매수 예약입니다."""

    signal_time: pd.Timestamp  # 반등 신호를 확인해 시장가 매수를 요청한 시각입니다.
    order_amount: float  # 다음 원본 봉 시가에 사용할 원화 주문 금액입니다.


def _infer_source_candle_duration(ohlcv: pd.DataFrame) -> pd.Timedelta:
    """원본 OHLCV 인덱스에서 한 캔들이 나타내는 최소 시간을 반환합니다."""

    intervals = ohlcv.index.to_series().diff().dropna()
    if intervals.empty or (intervals <= pd.Timedelta(0)).any():
        raise ValueError("OHLCV index must contain increasing candle timestamps.")
    return pd.Timedelta(intervals.min())


def _is_scheduled_execution_time(timestamp: pd.Timestamp, cron_duration: pd.Timedelta) -> bool:
    """자정 기준 V5 백테스트 크론 주기에 맞는 판단 시점인지 반환합니다."""

    return (timestamp - timestamp.normalize()) % cron_duration == pd.Timedelta(0)


def validate_ohlcv(ohlcv: pd.DataFrame, config: V5Config = V5_CONFIG) -> None:
    """V5 단타 백테스트에 필요한 OHLCV·수수료·크론 가정을 검증합니다.

    Args:
        ohlcv: ``open``·``high``·``low``·``close``와 시간순 인덱스를 가진 원본 5분봉입니다.
        config: V5 전략과 백테스트 자금·수수료·크론 가정을 담은 전체 설정입니다.

    Raises:
        ValueError: 필수 컬럼, 시간 인덱스, 자금·수수료·크론 설정이 유효하지 않을 때 발생합니다.
    """

    required_columns = {"open", "high", "low", "close"}
    missing_columns = required_columns - set(ohlcv.columns)
    if missing_columns:
        raise ValueError(f"OHLCV data is missing required columns: {', '.join(sorted(missing_columns))}")
    if not isinstance(ohlcv.index, pd.DatetimeIndex):
        raise ValueError("OHLCV index must be a DatetimeIndex.")
    if not ohlcv.index.is_monotonic_increasing or not ohlcv.index.is_unique or len(ohlcv) < 2:
        raise ValueError("OHLCV index must be unique, sorted, and contain at least two candles.")
    if config.backtest.initial_capital <= 0:
        raise ValueError("initial_capital must be greater than zero.")
    if not 0 <= config.fee_rate < 1:
        raise ValueError("fee_rate must be between 0 (inclusive) and 1 (exclusive).")
    if config.backtest.cron_interval_minutes <= 0:
        raise ValueError("cron_interval_minutes must be greater than zero.")
    source_duration = _infer_source_candle_duration(ohlcv)
    strategy_duration = pd.Timedelta(interval_to_timedelta(config.interval))
    cron_duration = pd.Timedelta(minutes=config.backtest.cron_interval_minutes)
    if source_duration != strategy_duration:
        raise ValueError("V5 source candles must use the same interval as the V5 strategy signal.")
    if cron_duration % source_duration != pd.Timedelta(0):
        raise ValueError("V5 cron interval must be a multiple of the strategy candle interval.")


def _close_position(
    cash: float,
    coin_amount: float,
    execution_price: float,
    fee_rate: float,
) -> tuple[float, float]:
    """보유 V5 물량 전부를 가상 매도하고 남은 원화·코인 수량을 반환합니다."""

    return cash + coin_amount * execution_price * (1 - fee_rate), 0.0


def run_backtest(
    ohlcv: pd.DataFrame,
    config: V5Config = V5_CONFIG,
    simulation_start: pd.Timestamp | None = None,
    simulation_end: pd.Timestamp | None = None,
) -> BacktestResult:
    """V5 반등·지정가 목표가·손절·시간 청산 규칙으로 자산 변화를 계산합니다.

    반등 신호는 완료된 원본 5분봉에서만 계산하고, 시장가 매수는 다음 5분봉의 시가로
    체결합니다. 목표가와 손절은 진입 뒤의 5분봉 고가·저가로 체결 여부를 판단하며,
    한 봉 안에 둘 다 닿았을 때는 보수적으로 손절을 먼저 적용합니다.

    Args:
        ohlcv: 시간순 완료 5분 OHLCV 데이터입니다.
        config: V5 티커·전략·백테스트 가정입니다.
        simulation_start: 원금을 적용하고 그래프에 표시할 포함 시각입니다.
        simulation_end: 그래프에 표시할 배타적 종료 시각입니다.

    Returns:
        RSI, 자산 곡선, 실제 가상 체결, 크론 판단 시각을 담은 결과입니다.

    Raises:
        ValueError: 입력 데이터·설정·기간이 유효하지 않을 때 발생합니다.
    """

    validate_ohlcv(ohlcv, config)
    if simulation_start is not None:
        simulation_start = pd.Timestamp(simulation_start)
    if simulation_end is not None:
        simulation_end = pd.Timestamp(simulation_end)
    if simulation_start is not None and simulation_end is not None and simulation_end <= simulation_start:
        raise ValueError("simulation_end must be later than simulation_start.")

    prices = ohlcv.copy()
    source_duration = _infer_source_candle_duration(prices)
    event_times = prices.index + source_duration
    close_prices = pd.Series(prices["close"].to_numpy(), index=event_times, name="close")
    rsi = pd.Series(index=event_times, dtype=float, name="RSI")
    signal_frame = calculate_signal_frame(prices, config.strategy)
    cash = config.backtest.initial_capital
    coin_amount = 0.0
    entry_price = 0.0
    entry_time: pd.Timestamp | None = None
    target_price = 0.0
    pending_entry: PendingEntry | None = None
    trades: list[BacktestTrade] = []
    evaluation_times: list[pd.Timestamp] = []
    equity_values: list[float] = []
    cron_duration = pd.Timedelta(minutes=config.backtest.cron_interval_minutes)

    for position, (candle_start, candle) in enumerate(prices.iterrows()):
        signal_time = candle_start + source_duration
        open_price = float(candle["open"])
        high_price = float(candle["high"])
        low_price = float(candle["low"])
        close_price = float(candle["close"])

        if pending_entry is not None and open_price > 0:
            order_amount = min(pending_entry.order_amount, cash)
            acquired_volume = order_amount * (1 - config.fee_rate) / open_price
            if acquired_volume > 0:
                cash -= order_amount
                coin_amount = acquired_volume
                entry_price = order_amount / acquired_volume
                entry_time = candle_start
                target_price = calculate_target_price(
                    order_amount,
                    acquired_volume,
                    config.fee_rate,
                    config.strategy.trade.target_net_profit_pct,
                )
                trades.append(
                    BacktestTrade(
                        action="BUY",
                        signal_time=pending_entry.signal_time,
                        execution_time=candle_start,
                        execution_price=open_price,
                        order_amount=order_amount,
                        profit_rate=0.0,
                    )
                )
            pending_entry = None

        if coin_amount > 0 and entry_time is not None:
            held_minutes = (signal_time - entry_time).total_seconds() / 60
            exit_decision = decide_exit(entry_price, close_price, held_minutes, config.strategy.trade)
            stop_price = exit_decision.stop_price
            exit_action = ""
            execution_price = 0.0
            # 한 봉의 저가·고가가 모두 기준을 통과하면 가격 순서를 알 수 없으므로 손절을 우선합니다.
            if open_price <= stop_price:
                exit_action, execution_price = "SELL_STOP_LOSS", open_price
            elif low_price <= stop_price:
                exit_action, execution_price = "SELL_STOP_LOSS", stop_price
            elif open_price >= target_price:
                exit_action, execution_price = "SELL_TARGET", open_price
            elif high_price >= target_price:
                exit_action, execution_price = "SELL_TARGET", target_price
            elif exit_decision.action == "SELL_TIME_EXIT":
                exit_action, execution_price = "SELL_TIME_EXIT", close_price
            if exit_action:
                profit_rate = (execution_price - entry_price) / entry_price * 100
                sold_amount = coin_amount
                cash, coin_amount = _close_position(
                    cash,
                    coin_amount,
                    execution_price,
                    config.fee_rate,
                )
                trades.append(
                    BacktestTrade(
                        action=exit_action,
                        signal_time=signal_time,
                        execution_time=signal_time,
                        execution_price=execution_price,
                        order_amount=sold_amount,
                        profit_rate=profit_rate,
                    )
                )
                entry_price = 0.0
                entry_time = None
                target_price = 0.0

        current_signal_row = signal_frame.iloc[position]
        previous_signal_row = signal_frame.iloc[position - 1] if position > 0 else None
        required_signal_values = (
            current_signal_row["rsi"],
            current_signal_row["lower_band"],
            current_signal_row["trend_sma"],
            previous_signal_row["rsi"] if previous_signal_row is not None else float("nan"),
            previous_signal_row["lower_band"] if previous_signal_row is not None else float("nan"),
        )
        if any(pd.isna(value) for value in required_signal_values):
            signal = None
        else:
            signal = SignalSnapshot(
                rsi=float(current_signal_row["rsi"]),
                previous_rsi=float(previous_signal_row["rsi"]),
                price=float(current_signal_row["price"]),
                previous_price=float(previous_signal_row["price"]),
                lower_band=float(current_signal_row["lower_band"]),
                previous_lower_band=float(previous_signal_row["lower_band"]),
                trend_sma=float(current_signal_row["trend_sma"]),
            )
            rsi.iloc[position] = signal.rsi

        equity_values.append(cash + coin_amount * close_price)
        if (
            signal is None
            or coin_amount > 0
            or position >= len(prices) - 1
            or (simulation_start is not None and signal_time < simulation_start)
            or (simulation_end is not None and signal_time >= simulation_end)
            or not _is_scheduled_execution_time(signal_time, cron_duration)
        ):
            continue

        evaluation_times.append(signal_time)
        decision = decide_entry(
            signal,
            cash,
            config.backtest.initial_capital,
            config.strategy,
        )
        if decision.action == "BUY":
            pending_entry = PendingEntry(signal_time, decision.order_amount)

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
    return BacktestResult(
        initial_capital=config.backtest.initial_capital,
        final_equity=final_equity,
        total_return_pct=(final_equity / config.backtest.initial_capital - 1) * 100,
        close_prices=close_prices,
        rsi=rsi,
        equity_curve=equity_curve,
        trades=trades,
        evaluation_times=evaluation_times,
    )
