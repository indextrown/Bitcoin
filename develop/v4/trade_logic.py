"""V4 RSI 회복 진입과 손익 관리의 순수 매매 판단 로직입니다."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from develop.upbit_develop_library import calculate_rsi_series


@dataclass(frozen=True)
class TradeConfig:
    """V4의 RSI 회복 진입·익절·손절·청산 기준입니다."""

    buy_threshold: float = 40.0  # 이전 RSI가 이 값 미만이고 현재 RSI가 이상이면 매수합니다.
    sell_threshold: float = 75.0  # 보유 중 RSI가 이 값 이상이면 전량 청산합니다.
    take_profit_pct: float = 3.0  # RSI와 무관하게 전량 익절할 최소 수익률(%)입니다.
    stop_loss_pct: float = 10.0  # RSI와 무관하게 전량 손절할 최대 손실률(%)입니다.
    buy_ratio: float = 1.0  # 회복 매수 때 가용 원화 중 사용할 비율입니다. (1.0 = 전액)
    min_trade_krw: float = 5_000.0  # 업비트 주문을 허용할 최소 주문 금액(KRW)입니다.


@dataclass(frozen=True)
class StrategyConfig:
    """V4 신호 생성과 매매 판단에 사용하는 전략 설정 묶음입니다."""

    rsi_period: int = 14  # RSI를 계산할 종가 캔들의 개수입니다.
    trade: TradeConfig = field(default_factory=TradeConfig)  # 회복 진입·청산 규칙입니다.


@dataclass(frozen=True)
class SignalSnapshot:
    """완료된 최신 전략 캔들의 현재·이전 RSI와 기준 가격입니다."""

    rsi: float  # 최신 전략 캔들에서 계산한 RSI 값입니다.
    previous_rsi: float  # 최신 전략 캔들 바로 이전의 RSI 값입니다.
    price: float  # 최신 전략 캔들의 종가입니다.


@dataclass(frozen=True)
class TradeDecision:
    """순수 매매 판단의 행동·주문 수량·수익률입니다."""

    action: str  # ``BUY``, ``SELL_STOP_LOSS``, ``SELL_TAKE_PROFIT``, ``SELL_RSI``, ``WAIT`` 중 하나입니다.
    order_amount: float = 0.0  # 매수면 원화 금액, 매도면 코인 수량입니다.
    profit_rate: float = 0.0  # 매도 판단에 사용한 평균 매수가 대비 수익률(%)입니다.


def build_signal(
    ohlcv: pd.DataFrame,
    config: StrategyConfig = StrategyConfig(),
) -> SignalSnapshot:
    """완료된 OHLCV 캔들에서 V4의 현재·이전 RSI와 기준 가격을 계산합니다.

    Args:
        ohlcv: ``close`` 컬럼을 가진 시간순 OHLCV 데이터입니다.
        config: RSI 기간과 V4 매매 설정입니다.

    Returns:
        현재 RSI, 이전 RSI, 최신 종가를 담은 신호입니다.

    Raises:
        ValueError: RSI 기간·종가 컬럼·캔들 수·RSI 준비 상태가 유효하지 않을 때 발생합니다.
    """

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
    previous_rsi: float,
    krw_balance: float,
    coin_amount: float,
    avg_buy_price: float,
    current_price: float,
    config: TradeConfig = TradeConfig(),
    max_order_krw: float | None = None,
) -> TradeDecision:
    """RSI 회복 신호와 보유 수익률로 V4의 다음 주문을 판단합니다.

    과매도 구간에 계속 머무를 때 여러 번 매수하는 대신, RSI가 ``buy_threshold``를
    아래에서 위로 회복할 때 한 번만 진입합니다. 보유 뒤에는 손절·익절을 먼저 적용하고,
    마지막으로 RSI 과매수 청산을 확인합니다.

    Args:
        rsi: 최신 전략 캔들에서 계산한 RSI 값입니다.
        previous_rsi: 최신 전략 캔들 바로 이전의 RSI 값입니다.
        krw_balance: 지금 주문에 사용할 수 있는 원화 잔고입니다.
        coin_amount: 현재 보유한 대상 코인의 수량입니다.
        avg_buy_price: 보유 코인의 평균 매수가입니다. 보유하지 않으면 ``0``입니다.
        current_price: 현재 신호가 기준으로 삼는 코인 가격입니다.
        config: V4의 RSI·익절·손절·주문 비율 기준입니다.
        max_order_krw: 공유 계좌에서 V4에 배정한 신규 매수 최대 원화입니다. ``None``이면
            기존처럼 가용 원화 잔고만 사용합니다.

    Returns:
        다음 행동과 주문 금액 또는 수량을 담은 순수 판단 결과입니다.
    """

    if coin_amount > 0:
        profit_rate = (
            (current_price - avg_buy_price) / avg_buy_price * 100
            if avg_buy_price > 0
            else 0.0
        )
        if profit_rate <= -config.stop_loss_pct:
            return TradeDecision("SELL_STOP_LOSS", order_amount=coin_amount, profit_rate=profit_rate)
        if profit_rate >= config.take_profit_pct:
            return TradeDecision("SELL_TAKE_PROFIT", order_amount=coin_amount, profit_rate=profit_rate)
        if rsi >= config.sell_threshold:
            return TradeDecision("SELL_RSI", order_amount=coin_amount, profit_rate=profit_rate)
        return TradeDecision("WAIT")

    is_rsi_recovery = previous_rsi < config.buy_threshold <= rsi
    budget_krw = min(krw_balance, max_order_krw) if max_order_krw is not None else krw_balance
    order_amount = budget_krw * config.buy_ratio
    if is_rsi_recovery and order_amount >= config.min_trade_krw:
        return TradeDecision("BUY", order_amount=order_amount)
    return TradeDecision("WAIT")
