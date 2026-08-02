"""V4.1의 추세 필터·쿨다운을 포함한 순수 매매 판단 로직입니다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from develop.upbit_develop_library import calculate_rsi_series


@dataclass(frozen=True)
class TradeConfig:
    """V4.1 RSI 회복 진입·추세 필터·손익 관리의 기준값입니다."""

    buy_threshold: float = 40.0  # 이전 RSI가 이 값 미만이고 현재 RSI가 이상이면 매수를 검토합니다.
    sell_threshold: float = 75.0  # 보유 중 RSI가 이 값 이상이면 전량 RSI 청산을 검토합니다.
    take_profit_pct: float = 3.0  # 평균 매수가 대비 이 수익률(%) 이상이면 전량 익절합니다.
    stop_loss_pct: float = 5.0  # 평균 매수가 대비 이 손실률(%) 이상이면 전량 손절합니다.
    buy_ratio: float = 1.0  # 매수 신호가 있을 때 가용 원화에서 사용할 비율입니다. (1.0 = 전액)
    min_trade_krw: float = 5_000.0  # 업비트 시장가 주문을 허용할 최소 주문 금액(KRW)입니다.
    require_uptrend: bool = True  # ``True``면 상승 추세가 확인된 RSI 회복 신호만 매수합니다.
    trend_sma_period: int = 50  # 4시간 전략 봉 종가로 계산할 추세 단순이동평균 기간입니다.
    cooldown_hours: int = 24  # 손절 체결 뒤 새 매수를 막을 시간(시간)입니다. (0 = 쿨다운 없음)


@dataclass(frozen=True)
class StrategyConfig:
    """V4.1 신호 생성과 순수 매매 판단에 사용하는 설정 묶음입니다."""

    rsi_period: int = 14  # RSI를 계산할 전략 봉 종가의 개수입니다.
    trade: TradeConfig = field(default_factory=TradeConfig)  # RSI·추세·손익 관리 기준입니다.


@dataclass(frozen=True)
class SignalSnapshot:
    """한 크론 실행 시점의 RSI·가격·추세 판단 입력값입니다."""

    rsi: float  # 최신 부분 전략 봉에서 계산한 RSI 값입니다.
    previous_rsi: float  # 최신 전략 봉 바로 전 전략 봉의 RSI 값입니다.
    price: float  # 최신 부분 전략 봉의 종가로, 수익률 계산 기준 가격입니다.
    trend_sma: float  # 최신 전략 봉까지 계산한 단순이동평균입니다.
    previous_trend_sma: float  # 최신 전략 봉 바로 전 시점의 단순이동평균입니다.


@dataclass(frozen=True)
class TradeDecision:
    """순수 매매 판단 결과와 주문에 사용할 수량 또는 금액입니다."""

    action: str  # ``BUY``, ``SELL_STOP_LOSS``, ``SELL_TAKE_PROFIT``, ``SELL_RSI``, ``WAIT`` 중 하나입니다.
    order_amount: float = 0.0  # 매수면 원화 금액, 매도면 보유 코인 수량입니다.
    profit_rate: float = 0.0  # 평균 매수가 대비 수익률(%)입니다.


def build_signal(
    ohlcv: pd.DataFrame,
    config: StrategyConfig = StrategyConfig(),
) -> SignalSnapshot:
    """시간순 전략 봉에서 V4.1의 RSI와 상승 추세 판단값을 계산합니다.

    Args:
        ohlcv: ``close`` 컬럼을 가진 시간순 전략 OHLCV 데이터입니다. 마지막 행은
            현재 크론 실행 시점까지 만들어진 부분 전략 봉일 수 있습니다.
        config: RSI 기간과 추세 이동평균 기간을 가진 V4.1 전략 설정입니다.

    Returns:
        현재·이전 RSI, 기준 가격, 현재·이전 추세 이동평균을 담은 신호입니다.

    Raises:
        ValueError: RSI·이동평균 기간, 종가 컬럼, 입력 봉 수, 계산 결과가 유효하지 않을 때 발생합니다.
    """

    if config.rsi_period < 1:
        raise ValueError("rsi_period must be greater than zero.")
    if config.trade.trend_sma_period < 1:
        raise ValueError("trend_sma_period must be greater than zero.")
    if "close" not in ohlcv.columns:
        raise ValueError("OHLCV data must include a close column.")

    required_rows = max(config.rsi_period + 2, config.trade.trend_sma_period + 1)
    if len(ohlcv) < required_rows:
        raise ValueError(f"At least {required_rows} OHLCV rows are required for the V4.1 signal.")

    rsi_series = calculate_rsi_series(ohlcv, period=config.rsi_period)
    trend_sma_series = ohlcv["close"].rolling(config.trade.trend_sma_period).mean()
    rsi = float(rsi_series.iloc[-1])
    previous_rsi = float(rsi_series.iloc[-2])
    trend_sma = float(trend_sma_series.iloc[-1])
    previous_trend_sma = float(trend_sma_series.iloc[-2])
    if any(pd.isna(value) for value in (rsi, previous_rsi, trend_sma, previous_trend_sma)):
        raise ValueError("RSI or trend SMA values are not ready yet.")
    return SignalSnapshot(
        rsi=rsi,
        previous_rsi=previous_rsi,
        price=float(ohlcv["close"].iloc[-1]),
        trend_sma=trend_sma,
        previous_trend_sma=previous_trend_sma,
    )


def is_uptrend(signal: SignalSnapshot) -> bool:
    """현재 가격이 추세 이동평균 위에 있는지 반환합니다.

    Args:
        signal: 현재 가격과 현재·이전 추세 이동평균을 담은 V4.1 신호입니다.

    Returns:
        가격이 현재 이동평균 이상이면 ``True``입니다.
    """

    return signal.price >= signal.trend_sma


def is_cooldown_active(
    decision_time: datetime,
    last_stop_loss_time: datetime | None,
    cooldown_hours: int,
) -> bool:
    """손절 뒤 재진입 금지 시간이 아직 남았는지 반환합니다.

    Args:
        decision_time: 지금 매매를 판단하는 시각입니다.
        last_stop_loss_time: 직전에 손절 주문이 실제로 체결된 시각입니다. 손절 이력이 없으면 ``None``입니다.
        cooldown_hours: 손절 체결 뒤 매수를 막을 시간입니다. 0이면 쿨다운을 사용하지 않습니다.

    Returns:
        새 매수를 막아야 하는 쿨다운 시간 안이면 ``True``입니다.
    """

    if cooldown_hours < 0:
        raise ValueError("cooldown_hours must not be negative.")
    if last_stop_loss_time is None or cooldown_hours == 0:
        return False
    return decision_time < last_stop_loss_time + timedelta(hours=cooldown_hours)


def decide_trade(
    signal: SignalSnapshot,
    krw_balance: float,
    coin_amount: float,
    avg_buy_price: float,
    decision_time: datetime,
    last_stop_loss_time: datetime | None,
    config: TradeConfig = TradeConfig(),
) -> TradeDecision:
    """V4.1의 보유 청산과 추세 확인 회복 매수를 순수하게 판단합니다.

    보유 중일 때는 손절·익절·RSI 청산을 추세나 쿨다운보다 먼저 적용합니다. 미보유 상태에서는
    RSI 회복, 상승 추세, 손절 뒤 쿨다운 종료를 모두 만족해야만 매수합니다.

    Args:
        signal: 현재·이전 RSI, 가격, 추세 이동평균을 담은 신호입니다.
        krw_balance: 현재 주문에 사용할 수 있는 원화 잔고입니다.
        coin_amount: 현재 보유한 대상 코인의 수량입니다.
        avg_buy_price: 보유 코인의 평균 매수가입니다. 미보유 상태에서는 ``0``입니다.
        decision_time: 지금 주문을 판단하는 시각입니다.
        last_stop_loss_time: 직전 손절 주문의 체결 시각입니다. 손절 이력이 없으면 ``None``입니다.
        config: RSI·추세·수익률·주문 비율·쿨다운 기준입니다.

    Returns:
        다음 행동과 주문 금액 또는 수량을 담은 판단 결과입니다.
    """

    if coin_amount > 0:
        profit_rate = (
            (signal.price - avg_buy_price) / avg_buy_price * 100
            if avg_buy_price > 0
            else 0.0
        )
        if profit_rate <= -config.stop_loss_pct:
            return TradeDecision("SELL_STOP_LOSS", order_amount=coin_amount, profit_rate=profit_rate)
        if profit_rate >= config.take_profit_pct:
            return TradeDecision("SELL_TAKE_PROFIT", order_amount=coin_amount, profit_rate=profit_rate)
        if signal.rsi >= config.sell_threshold:
            return TradeDecision("SELL_RSI", order_amount=coin_amount, profit_rate=profit_rate)
        return TradeDecision("WAIT")

    recovered = signal.previous_rsi < config.buy_threshold <= signal.rsi
    trend_confirmed = is_uptrend(signal) if config.require_uptrend else True
    order_amount = krw_balance * config.buy_ratio
    if (
        recovered
        and trend_confirmed
        and not is_cooldown_active(decision_time, last_stop_loss_time, config.cooldown_hours)
        and order_amount >= config.min_trade_krw
    ):
        return TradeDecision("BUY", order_amount=order_amount)
    return TradeDecision("WAIT")
