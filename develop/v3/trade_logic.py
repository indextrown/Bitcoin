"""V3 RSI 봇의 순수 매매 판단 로직입니다."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from develop.upbit_develop_library import calculate_rsi_series


@dataclass(frozen=True)
class TradeConfig:
    """RSI 기반 매수·매도·익절 판단에 사용하는 기준값입니다."""

    buy_threshold: float = 30.0
    sell_threshold: float = 70.0
    sell_profit_pct: float = 5.0
    buy_ratio: float = 0.2
    min_trade_krw: float = 5_000.0


@dataclass(frozen=True)
class StrategyConfig:
    """V3 신호 생성과 매매 판단에 사용하는 전략 설정 묶음입니다."""

    rsi_period: int = 14
    trade: TradeConfig = field(default_factory=TradeConfig)


@dataclass(frozen=True)
class SignalSnapshot:
    """완료된 최신 캔들에서 계산한 가격 및 RSI 신호값입니다."""

    rsi: float
    previous_rsi: float
    price: float


@dataclass(frozen=True)
class TradeDecision:
    """순수 매매 판단의 결과와 주문에 사용할 수량 또는 금액입니다."""

    action: str
    order_amount: float = 0.0
    profit_rate: float = 0.0


def build_signal(
    ohlcv: pd.DataFrame,
    config: StrategyConfig = StrategyConfig(),
) -> SignalSnapshot:
    """완료된 OHLCV 캔들에서 V3의 RSI·이전 RSI·현재가를 계산합니다."""

    if config.rsi_period < 1:
        raise ValueError("rsi_period must be greater than zero.")
    if "close" not in ohlcv.columns:
        raise ValueError("OHLCV data must include a close column.")
    if len(ohlcv) < config.rsi_period + 2:
        raise ValueError(
            f"At least {config.rsi_period + 2} OHLCV rows are required for RSI({config.rsi_period})."
        )

    rsi = calculate_rsi_series(ohlcv, period=config.rsi_period)
    current_rsi = float(rsi.iloc[-1])
    previous_rsi = float(rsi.iloc[-2])
    if pd.isna(current_rsi) or pd.isna(previous_rsi):
        raise ValueError("RSI values are not ready yet.")
    return SignalSnapshot(
        rsi=current_rsi,
        previous_rsi=previous_rsi,
        price=float(ohlcv["close"].iloc[-1]),
    )


def decide_trade(
    rsi: float,
    krw_balance: float,
    coin_amount: float,
    avg_buy_price: float,
    current_price: float,
    config: TradeConfig = TradeConfig(),
) -> TradeDecision:
    """현재 RSI와 잔고를 바탕으로 V3의 다음 주문을 판단합니다.

    이 함수는 거래소 API를 호출하지 않으므로 단위 테스트와 실제 주문 실행에서
    같은 판단 규칙을 안전하게 공유할 수 있습니다.
    """

    if rsi <= config.buy_threshold and krw_balance > config.min_trade_krw:
        order_amount = krw_balance * config.buy_ratio
        if order_amount >= config.min_trade_krw:
            return TradeDecision("BUY", order_amount=order_amount)

    if rsi >= config.sell_threshold and coin_amount > 0:
        profit_rate = (
            (current_price - avg_buy_price) / avg_buy_price * 100
            if avg_buy_price > 0
            else 0.0
        )
        if profit_rate <= 0:
            return TradeDecision(
                "SELL_LOSS",
                order_amount=coin_amount,
                profit_rate=profit_rate,
            )
        if profit_rate >= config.sell_profit_pct:
            return TradeDecision(
                "SELL_PROFIT",
                order_amount=coin_amount,
                profit_rate=profit_rate,
            )

    return TradeDecision("WAIT")
