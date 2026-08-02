"""V5의 짧은 반등 진입·목표가 계산·손절 판단을 담은 순수 함수입니다."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

import pandas as pd

from develop.upbit_develop_library import calculate_rsi_series


@dataclass(frozen=True)
class TradeConfig:
    """V5 단타의 목표 순이익·손실 제한·주문 금액 기준입니다."""

    target_net_profit_pct: float = 0.1  # 매수·매도 수수료 뒤 원금 대비 목표로 남기려는 순이익률(%)입니다.
    stop_loss_pct: float = 1.0  # 평균 진입가보다 이 비율(%) 이상 내리면 시장가 손절합니다.
    max_hold_minutes: int = 90  # 목표가가 체결되지 않았을 때 보유를 허용할 최대 시간(분)입니다.
    buy_ratio: float = 1.0  # V5에 할당된 주문 한도 중 이번 진입에 사용할 비율입니다. (1.0 = 전액)
    min_trade_krw: float = 5_000.0  # 업비트 KRW 주문을 허용할 최소 주문 금액입니다.


@dataclass(frozen=True)
class StrategyConfig:
    """V5의 5분봉 반등 신호와 단타 청산 규칙을 묶습니다."""

    rsi_period: int = 7  # 짧은 반등 힘을 계산할 RSI의 캔들 개수입니다.
    entry_rsi_threshold: float = 40.0  # 이전 RSI가 아래이고 현재 RSI가 위로 회복해야 하는 기준입니다.
    bollinger_period: int = 20  # 하단 밴드를 계산할 종가 이동평균 기간입니다.
    bollinger_stddev: float = 2.5  # 평소 변동에는 진입하지 않도록 하단 밴드에 적용할 표준편차 배수입니다.
    trend_sma_period: int = 50  # 큰 하락 추세를 거를 기준으로 삼을 5분봉 단순이동평균 기간입니다.
    require_price_above_trend_sma: bool = True  # ``True``면 최신 종가가 장기 SMA 위일 때만 진입합니다.
    trade: TradeConfig = field(default_factory=TradeConfig)  # 수익 목표·손절·최대 보유 시간 규칙입니다.


@dataclass(frozen=True)
class SignalSnapshot:
    """V5 진입 판단에 필요한 최신·이전 RSI와 하단 볼린저 밴드 값입니다."""

    rsi: float  # 최신 완료 캔들의 RSI 값입니다.
    previous_rsi: float  # 최신 완료 캔들 바로 전의 RSI 값입니다.
    price: float  # 최신 완료 캔들의 종가입니다.
    previous_price: float  # 최신 완료 캔들 바로 전의 종가입니다.
    lower_band: float  # 최신 완료 캔들의 하단 볼린저 밴드 가격입니다.
    previous_lower_band: float  # 최신 완료 캔들 바로 전의 하단 볼린저 밴드 가격입니다.
    trend_sma: float  # 최신 완료 캔들의 장기 추세 확인용 단순이동평균 가격입니다.


@dataclass(frozen=True)
class TradeDecision:
    """V5 순수 판단이 돌려주는 다음 행동과 주문 금액입니다."""

    action: str  # ``BUY``, ``SELL_STOP_LOSS``, ``SELL_TIME_EXIT``, ``WAIT`` 중 하나입니다.
    order_amount: float = 0.0  # 매수면 원화 금액, 이 전략의 매도 판단에서는 사용하지 않습니다.
    stop_price: float = 0.0  # 손절 판단에 사용한 가격입니다.


def _validate_signal_input(ohlcv: pd.DataFrame, config: StrategyConfig) -> int:
    """V5 RSI·볼린저 밴드·추세 SMA 계산에 필요한 입력을 검증하고 최소 봉 수를 반환합니다."""

    if "close" not in ohlcv.columns:
        raise ValueError("OHLCV data must include a close column.")
    if (
        config.rsi_period < 1
        or config.bollinger_period < 2
        or config.bollinger_stddev <= 0
        or config.trend_sma_period < 2
    ):
        raise ValueError("V5 RSI, Bollinger, and trend SMA settings must be positive.")
    return max(
        config.rsi_period + 2,
        config.bollinger_period + 1,
        config.trend_sma_period,
    )


def calculate_signal_frame(
    ohlcv: pd.DataFrame,
    config: StrategyConfig = StrategyConfig(),
) -> pd.DataFrame:
    """전체 OHLCV에서 V5 RSI·하단 밴드·추세 SMA 시계열을 한 번에 계산합니다.

    ``build_signal``은 최신 한 지점만 필요할 때, 백테스트는 모든 지점의 지표가 필요할
    때 이 함수를 함께 사용합니다. 계산 결과의 앞부분에는 RSI·이동평균 준비에 필요한
    만큼 ``NaN``이 남을 수 있습니다.

    Args:
        ohlcv: ``close`` 컬럼을 가진 시간순 완료 OHLCV 데이터입니다.
        config: RSI·볼린저 밴드·추세 SMA 설정입니다.

    Returns:
        입력과 같은 인덱스에 ``rsi``, ``price``, ``lower_band``, ``trend_sma``를 담은 프레임입니다.
    """

    _validate_signal_input(ohlcv, config)
    close = ohlcv["close"].astype(float)
    moving_average = close.rolling(config.bollinger_period).mean()
    standard_deviation = close.rolling(config.bollinger_period).std(ddof=0)
    return pd.DataFrame(
        {
            "rsi": calculate_rsi_series(ohlcv, period=config.rsi_period),
            "price": close,
            "lower_band": moving_average - config.bollinger_stddev * standard_deviation,
            "trend_sma": close.rolling(config.trend_sma_period).mean(),
        },
        index=ohlcv.index,
    )


def build_signal(
    ohlcv: pd.DataFrame,
    config: StrategyConfig = StrategyConfig(),
) -> SignalSnapshot:
    """완료된 OHLCV에서 V5의 RSI 회복·하단 밴드 반등 신호를 계산합니다.

    Args:
        ohlcv: ``close`` 컬럼을 가진 시간순 완료 OHLCV 데이터입니다.
        config: RSI·볼린저 밴드 기간과 진입 기준입니다.

    Returns:
        최신과 이전의 RSI·종가·하단 밴드를 담은 신호입니다.

    Raises:
        ValueError: 필수 컬럼, RSI·밴드·추세 설정값, 준비된 캔들 수가 유효하지 않을 때 발생합니다.
    """

    required_rows = _validate_signal_input(ohlcv, config)
    if len(ohlcv) < required_rows:
        raise ValueError(f"At least {required_rows} OHLCV rows are required for the V5 signal.")

    signal_frame = calculate_signal_frame(ohlcv, config)
    values = (
        signal_frame["rsi"].iloc[-1],
        signal_frame["rsi"].iloc[-2],
        signal_frame["lower_band"].iloc[-1],
        signal_frame["lower_band"].iloc[-2],
        signal_frame["trend_sma"].iloc[-1],
    )
    if any(pd.isna(value) for value in values):
        raise ValueError("V5 RSI or Bollinger values are not ready yet.")
    return SignalSnapshot(
        rsi=float(signal_frame["rsi"].iloc[-1]),
        previous_rsi=float(signal_frame["rsi"].iloc[-2]),
        price=float(signal_frame["price"].iloc[-1]),
        previous_price=float(signal_frame["price"].iloc[-2]),
        lower_band=float(signal_frame["lower_band"].iloc[-1]),
        previous_lower_band=float(signal_frame["lower_band"].iloc[-2]),
        trend_sma=float(signal_frame["trend_sma"].iloc[-1]),
    )


def decide_entry(
    signal: SignalSnapshot,
    krw_balance: float,
    max_order_krw: float,
    config: StrategyConfig = StrategyConfig(),
) -> TradeDecision:
    """RSI·하단 밴드 반등과 V5 자금 한도로 신규 단타 진입을 판단합니다.

    이전 캔들이 하단 밴드 아래에서 마감하고 RSI도 기준 아래였으며, 최신 완료 캔들이
    RSI 기준 위로 회복한 경우에만 진입합니다. 주문 금액은 실제 원화 잔고와 V5 전용
    한도 중 작은 값으로 제한하므로 V4의 ETH 자금을 침범하지 않습니다.

    Args:
        signal: ``build_signal``이 만든 최신 반등 신호입니다.
        krw_balance: 현재 업비트에서 주문할 수 있는 원화 잔고입니다.
        max_order_krw: 포트폴리오에서 V5에 배정한 신규 매수 최대 원화입니다.
        config: V5의 RSI·밴드·주문 비율 설정입니다.

    Returns:
        신규 매수 또는 대기 행동과 매수 원화 금액입니다.
    """

    budget_krw = max(0.0, min(krw_balance, max_order_krw))
    order_amount = budget_krw * config.trade.buy_ratio
    is_rsi_recovery = signal.previous_rsi < config.entry_rsi_threshold <= signal.rsi
    is_lower_band_rebound = (
        signal.previous_price <= signal.previous_lower_band and signal.price >= signal.lower_band
    )
    is_uptrend = not config.require_price_above_trend_sma or signal.price >= signal.trend_sma
    if is_rsi_recovery and is_lower_band_rebound and is_uptrend and order_amount >= config.trade.min_trade_krw:
        return TradeDecision("BUY", order_amount=order_amount)
    return TradeDecision("WAIT")


def decide_exit(
    entry_price: float,
    current_price: float,
    held_minutes: float,
    config: TradeConfig = TradeConfig(),
) -> TradeDecision:
    """보유 중인 V5 물량의 시장가 손절 또는 시간 청산 여부를 판단합니다.

    목표가 익절은 업비트 지정가 매도 주문으로 미리 맡기므로 여기서는 판단하지 않습니다.
    손절과 시간 청산은 지정가 주문을 취소한 뒤 시장가 매도로 실행됩니다.

    Args:
        entry_price: 실제 체결된 평균 진입가입니다.
        current_price: 현재 시장가입니다.
        held_minutes: 실제 진입 뒤 경과한 시간(분)입니다.
        config: 손절률과 최대 보유 시간을 담은 V5 거래 설정입니다.

    Returns:
        손절, 시간 청산, 대기 중 하나의 행동입니다.
    """

    if entry_price <= 0:
        raise ValueError("entry_price must be greater than zero.")
    if held_minutes < 0:
        raise ValueError("held_minutes must not be negative.")
    stop_price = entry_price * (1 - config.stop_loss_pct / 100)
    if current_price <= stop_price:
        return TradeDecision("SELL_STOP_LOSS", stop_price=stop_price)
    if held_minutes >= config.max_hold_minutes:
        return TradeDecision("SELL_TIME_EXIT")
    return TradeDecision("WAIT", stop_price=stop_price)


def get_krw_price_tick(price: float) -> float:
    """KRW 마켓의 가격 구간별 호가 단위를 반환합니다.

    Args:
        price: 호가 단위를 확인할 주문 가격입니다.

    Returns:
        이 가격에서 업비트 KRW 마켓이 허용하는 최소 가격 변화 단위입니다.

    Raises:
        ValueError: 가격이 0 이하일 때 발생합니다.
    """

    if price <= 0:
        raise ValueError("price must be greater than zero.")
    for minimum_price, tick in (
        (2_000_000.0, 1_000.0),
        (1_000_000.0, 1_000.0),
        (500_000.0, 500.0),
        (100_000.0, 100.0),
        (50_000.0, 50.0),
        (10_000.0, 10.0),
        (5_000.0, 5.0),
        (1_000.0, 1.0),
        (100.0, 1.0),
        (10.0, 0.1),
        (1.0, 0.01),
        (0.1, 0.001),
        (0.01, 0.0001),
        (0.001, 0.00001),
    ):
        if price >= minimum_price:
            return tick
    return 0.000001


def calculate_target_price(
    entry_cost_krw: float,
    acquired_volume: float,
    fee_rate: float,
    target_net_profit_pct: float,
) -> float:
    """매수·매도 수수료 뒤 목표 순이익률을 남길 지정가 매도 가격을 계산합니다.

    Args:
        entry_cost_krw: 실제 시장가 매수에 사용한 원화입니다. 매수 수수료를 포함합니다.
        acquired_volume: 매수 수수료가 차감된 뒤 실제 보유한 코인 수량입니다.
        fee_rate: 매도 시 적용할 수수료 비율입니다.
        target_net_profit_pct: 매도 수수료 뒤 원금 대비 더 남기려는 순이익률(%)입니다.

    Returns:
        KRW 호가 단위로 올림한 지정가 매도 가격입니다.

    Raises:
        ValueError: 원금·수량·수수료·목표 순이익률이 유효하지 않을 때 발생합니다.
    """

    if entry_cost_krw <= 0 or acquired_volume <= 0:
        raise ValueError("entry_cost_krw and acquired_volume must be greater than zero.")
    if not 0 <= fee_rate < 1:
        raise ValueError("fee_rate must be between 0 (inclusive) and 1 (exclusive).")
    if target_net_profit_pct < 0:
        raise ValueError("target_net_profit_pct must not be negative.")
    target_net_profit_krw = entry_cost_krw * target_net_profit_pct / 100
    raw_price = (entry_cost_krw + target_net_profit_krw) / (acquired_volume * (1 - fee_rate))
    tick = get_krw_price_tick(raw_price)
    return ceil(raw_price / tick) * tick
