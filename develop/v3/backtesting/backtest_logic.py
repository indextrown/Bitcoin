"""V3 전략을 과거 OHLCV 데이터에 적용하는 순수 백테스트 로직입니다."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import pandas as pd

from develop.v3.config import V3_CONFIG, V3Config, interval_to_timedelta
from develop.v3.trade_logic import build_signal, decide_trade


@dataclass(frozen=True)
class BacktestTrade:
    """원본 봉 종료 시점의 다음 원본 봉 시가 체결을 기록한 주문입니다."""

    action: str  # ``BUY``, ``SELL_LOSS``, ``SELL_PROFIT`` 중 실제 체결한 행동입니다.
    signal_time: pd.Timestamp  # RSI 신호를 계산하고 주문을 판단한 원본 봉 종료 시각입니다.
    execution_time: pd.Timestamp  # 다음 원본 봉 시가로 체결했다고 가정한 시각입니다.
    execution_price: float  # 가상 체결에 적용한 다음 원본 봉의 시가입니다.
    order_amount: float  # 매수면 원화 금액, 매도면 코인 수량입니다.
    profit_rate: float  # 매도 판단 시 평균 매수가 기준 수익률(%)입니다.


@dataclass(frozen=True)
class BacktestResult:
    """순수 백테스트가 반환하는 거래 기록, RSI, 자산 변화 결과입니다."""

    initial_capital: float  # 시작 원화 자산입니다.
    final_equity: float  # 마지막 원본 봉 종료 시점의 원화 환산 총자산입니다.
    total_return_pct: float  # 시작 자산 대비 최종 수익률(%)입니다.
    close_prices: pd.Series  # 표시 기간의 원본 봉 종가 시계열입니다.
    rsi: pd.Series  # 각 원본 봉 종료 시점에 계산한 RSI 시계열입니다.
    equity_curve: pd.Series  # 각 원본 봉 종료 시점의 원화 환산 총자산 시계열입니다.
    trades: list[BacktestTrade]  # 시뮬레이션에서 실제로 체결된 주문 기록입니다.
    evaluation_times: list[pd.Timestamp]  # 크론 가정에 따라 매매 판단을 실행한 시각입니다.


def select_source_interval(cron_interval_minutes: int) -> str:
    """크론 가정을 재현할 수 있는 가장 긴 업비트 원본 캔들 간격을 고릅니다.

    예를 들어 30분 크론은 ``minute30`` 원본을, 90분 크론은 ``minute30`` 원본을
    사용합니다. 원본 간격은 크론 주기를 정확히 나눌 수 있어야 각 실행 시점을
    미래 데이터 없이 재현할 수 있습니다.

    Args:
        cron_interval_minutes: 시뮬레이터가 봇을 실행한다고 가정할 분 단위 간격입니다.

    Returns:
        크론 간격을 나누는 가장 긴 업비트 ``minuteN`` 원본 캔들 간격입니다.

    Raises:
        ValueError: 크론 간격이 0 이하일 때 발생합니다.
    """

    if cron_interval_minutes <= 0:
        raise ValueError("cron_interval_minutes must be greater than zero.")

    for minutes in (240, 60, 30, 15, 10, 5, 3, 1):
        if cron_interval_minutes % minutes == 0:
            return f"minute{minutes}"
    raise AssertionError("minute1 must divide every positive integer.")


def calculate_source_count(
    strategy_interval: str,
    source_interval: str,
    strategy_candle_count: int,
) -> int:
    """전략 봉 개수만큼의 기간을 덮는 원본 캔들 조회 개수를 계산합니다.

    Args:
        strategy_interval: RSI 전략이 사용할 업비트 캔들 간격입니다.
        source_interval: 크론 실행 시점 재현에 사용할 더 짧은 업비트 캔들 간격입니다.
        strategy_candle_count: 그래프와 RSI 계산에 확보할 전략 봉의 목표 개수입니다.

    Returns:
        ``source_interval``로 업비트에서 조회해야 할 원본 봉 개수입니다.

    Raises:
        ValueError: 요청 봉 수가 0 이하이거나 원본 봉이 전략 봉보다 길 때 발생합니다.
    """

    if strategy_candle_count <= 0:
        raise ValueError("strategy_candle_count must be greater than zero.")

    strategy_duration = interval_to_timedelta(strategy_interval)
    source_duration = interval_to_timedelta(source_interval)
    if source_duration > strategy_duration:
        raise ValueError("source_interval must not be longer than strategy_interval.")

    return ceil(strategy_duration / source_duration) * strategy_candle_count + 1


def calculate_period_source_count(
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
    source_interval: str,
    strategy_interval: str,
    rsi_period: int,
) -> int:
    """날짜 지정 백테스트에 필요한 원본 봉 수와 RSI 준비 구간을 계산합니다.

    Args:
        start_time: 그래프·가상 자산 계산을 시작할 포함 시각입니다.
        end_time: 그래프·가상 자산 계산을 끝낼 배타적 시각입니다.
        source_interval: 크론 실행 시점 재현에 사용하는 짧은 업비트 캔들 간격입니다.
        strategy_interval: RSI 전략이 사용하는 긴 업비트 캔들 간격입니다.
        rsi_period: RSI 계산에 필요한 전략 봉 수입니다.

    Returns:
        지정 기간과 RSI 준비 구간을 함께 포함하도록 조회할 원본 봉 개수입니다.

    Raises:
        ValueError: 기간 순서나 RSI 기간이 유효하지 않을 때 발생합니다.
    """

    if end_time <= start_time:
        raise ValueError("end_time must be later than start_time.")
    if rsi_period < 1:
        raise ValueError("rsi_period must be greater than zero.")

    source_duration = pd.Timedelta(interval_to_timedelta(source_interval))
    strategy_duration = pd.Timedelta(interval_to_timedelta(strategy_interval))
    period_duration = end_time - start_time
    warmup_duration = strategy_duration * (rsi_period + 2)
    return ceil((period_duration + warmup_duration) / source_duration) + 1


def build_strategy_ohlcv(
    source_ohlcv: pd.DataFrame,
    strategy_interval: str,
    strategy_candle_anchor: pd.Timestamp,
) -> pd.DataFrame:
    """실행 시점까지의 짧은 봉을 전략 봉으로 묶어 RSI 입력 데이터를 만듭니다.

    마지막 전략 봉은 아직 진행 중인 부분 봉일 수 있습니다. 이는 크론으로 실행된
    실제 봇이 해당 시점에 ``pyupbit.get_ohlcv(..., interval=전략봉)``로 보는 값과
    같은 종류의 스냅샷을 만들기 위한 처리입니다. ``strategy_candle_anchor``는
    업비트가 해당 전략 봉을 시작한 시각이므로, 단순히 자정 기준으로 묶어 실제
    거래소의 봉 경계가 달라지는 문제를 막습니다.

    Args:
        source_ohlcv: 현재 실행 시점까지 완료된 짧은 원본 봉 데이터입니다.
        strategy_interval: 이 원본 봉을 묶어 만들 RSI 전략 봉 간격입니다.
        strategy_candle_anchor: 업비트가 실제 전략 봉을 시작한 시각입니다.

    Returns:
        전략 봉 경계를 맞춰 합친 ``open``·``close`` OHLCV 데이터입니다.
    """

    strategy_duration = pd.Timedelta(interval_to_timedelta(strategy_interval))
    anchor = pd.Timestamp(strategy_candle_anchor)
    bucket_start = (source_ohlcv.index - anchor).floor(strategy_duration) + anchor
    return source_ohlcv.groupby(bucket_start, sort=True).agg(
        open=("open", "first"),
        close=("close", "last"),
    )


def _infer_source_candle_duration(ohlcv: pd.DataFrame) -> pd.Timedelta:
    """원본 OHLCV 인덱스에서 한 캔들이 나타내는 시간을 추정합니다.

    Args:
        ohlcv: 시간순 ``DatetimeIndex``를 가진 원본 봉 데이터입니다.

    Returns:
        인접한 원본 봉 시작 시각 사이의 최소 시간 간격입니다.

    Raises:
        ValueError: 시각 인덱스가 증가하지 않거나 봉이 하나뿐일 때 발생합니다.
    """

    intervals = ohlcv.index.to_series().diff().dropna()
    if intervals.empty or (intervals <= pd.Timedelta(0)).any():
        raise ValueError("OHLCV index must contain increasing candle timestamps.")
    return pd.Timedelta(intervals.min())


def _is_scheduled_execution_time(timestamp: pd.Timestamp, cron_duration: pd.Timedelta) -> bool:
    """자정 기준 크론 주기에 맞는 실행 시점인지 반환합니다.

    Args:
        timestamp: 원본 봉이 종료되어 시뮬레이터가 판단할 수 있는 시각입니다.
        cron_duration: 백테스트에서 가정한 봇 실행 주기입니다.

    Returns:
        해당 시각이 자정 기준 크론 실행 시점이면 ``True``입니다.
    """

    elapsed_today = timestamp - timestamp.normalize()
    return elapsed_today % cron_duration == pd.Timedelta(0)


def validate_ohlcv(ohlcv: pd.DataFrame, config: V3Config = V3_CONFIG) -> None:
    """원본 OHLCV와 백테스트 크론 가정이 함께 유효한지 확인합니다.

    Args:
        ohlcv: ``open``·``close`` 컬럼과 시간순 ``DatetimeIndex``를 가진 원본 봉 데이터입니다.
        config: 전략 간격과 백테스트 자금·수수료·크론 가정을 담은 V3 전체 설정입니다.

    Raises:
        ValueError: 입력 컬럼, 시각 순서, 체결 가정, 크론 간격이 유효하지 않을 때 발생합니다.
    """

    required_columns = {"open", "close"}
    missing_columns = required_columns - set(ohlcv.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"OHLCV data is missing required columns: {missing}")

    if not isinstance(ohlcv.index, pd.DatetimeIndex):
        raise ValueError("OHLCV index must be a DatetimeIndex.")
    if not ohlcv.index.is_monotonic_increasing or not ohlcv.index.is_unique:
        raise ValueError("OHLCV index must be unique and sorted in ascending order.")
    if len(ohlcv) < 2:
        raise ValueError("At least two OHLCV rows are required for backtesting.")
    if config.backtest.initial_capital <= 0:
        raise ValueError("initial_capital must be greater than zero.")
    if not 0 <= config.backtest.fee_rate < 1:
        raise ValueError("fee_rate must be between 0 (inclusive) and 1 (exclusive).")
    if config.backtest.cron_interval_minutes <= 0:
        raise ValueError("cron_interval_minutes must be greater than zero.")

    source_duration = _infer_source_candle_duration(ohlcv)
    cron_duration = pd.Timedelta(minutes=config.backtest.cron_interval_minutes)
    if source_duration > cron_duration or cron_duration % source_duration != pd.Timedelta(0):
        raise ValueError(
            "OHLCV source candles must be no longer than and evenly divide the cron interval."
        )


def run_backtest(
    ohlcv: pd.DataFrame,
    config: V3Config = V3_CONFIG,
    strategy_candle_anchor: pd.Timestamp | None = None,
    simulation_start: pd.Timestamp | None = None,
    simulation_end: pd.Timestamp | None = None,
) -> BacktestResult:
    """OHLCV와 V3 설정만으로 크론 실행을 가정한 체결·자산 변화를 계산합니다.

    원본 OHLCV의 크론 실행 시점마다 진행 중인 전략 봉을 만들어 같은
    ``build_signal``·``decide_trade`` 로직을 실행합니다. 주문은 미래 정보를 쓰지
    않도록 다음 원본 캔들의 시가에 체결된다고 가정합니다. 외부 API 호출이나 파일
    저장은 하지 않습니다. 실제 업비트 백테스트에서는 ``strategy_candle_anchor``에
    업비트 전략 봉의 시작 시각을 넘겨야 합니다.

    Args:
        ohlcv: 크론 실행 시점보다 같거나 짧은 간격의 시간순 원본 OHLCV 데이터입니다.
        config: 티커·전략·백테스트 체결 가정을 가진 V3 설정입니다.
        strategy_candle_anchor: 업비트가 현재 전략 봉을 시작한 시각입니다. 거래소의
            실제 전략 봉 경계에 맞춰 원본 봉을 합치기 위해 필요합니다.
        simulation_start: 시작 자산을 적용하고 그래프에 표시할 포함 시각입니다. 이보다
            이전 데이터는 RSI 준비에만 사용하며 가상 주문은 실행하지 않습니다.
        simulation_end: 그래프에 표시할 배타적 종료 시각입니다. ``None``이면 원본
            데이터의 마지막까지 사용합니다.

    Returns:
        RSI, 자산 곡선, 체결 기록, 판단 시각을 담은 백테스트 결과입니다.

    Raises:
        ValueError: OHLCV·백테스트 설정이 유효하지 않거나 전략 봉 기준 시각이 없을 때 발생합니다.
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
    avg_buy_price = 0.0
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
        if len(strategy_ohlcv) < config.strategy.rsi_period + 2:
            continue
        signal = build_signal(strategy_ohlcv, config.strategy)
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
            signal.rsi,
            cash,
            coin_amount,
            avg_buy_price,
            signal.price,
            config.strategy.trade,
        )
        if decision.action == "WAIT":
            continue

        execution_candle = prices.iloc[position + 1]
        execution_time = signal_time
        execution_price = float(execution_candle["open"])
        if execution_price <= 0:
            continue

        if decision.action == "BUY":
            order_amount = min(decision.order_amount, cash)
            bought_amount = order_amount * (1 - config.backtest.fee_rate) / execution_price
            if bought_amount <= 0:
                continue

            total_cost = avg_buy_price * coin_amount + order_amount
            cash -= order_amount
            coin_amount += bought_amount
            avg_buy_price = total_cost / coin_amount
        else:
            order_amount = min(decision.order_amount, coin_amount)
            if order_amount <= 0:
                continue

            cash += order_amount * execution_price * (1 - config.backtest.fee_rate)
            coin_amount -= order_amount
            if coin_amount <= 0:
                coin_amount = 0.0
                avg_buy_price = 0.0

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
