"""V3 RSI 봇의 순수 매매 판단 로직입니다."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from develop.upbit_develop_library import calculate_rsi_series


@dataclass(frozen=True)
class TradeConfig:
    """RSI 기반 매수·매도·익절 판단에 사용하는 기준값입니다."""

    buy_threshold: float = 30.0  # RSI가 이 값 이하이면 매수를 검토합니다.
    sell_threshold: float = 70.0  # RSI가 이 값 이상이면 매도를 검토합니다.
    sell_profit_pct: float = 5.0  # 익절 매도에 필요한 최소 수익률(%)입니다.
    buy_ratio: float = 0.2  # 매수 시 가용 원화 잔고에서 사용할 비율입니다. (0.2 = 20%)
    min_trade_krw: float = 5_000.0  # 업비트 주문을 허용할 최소 주문 금액(KRW)입니다.


@dataclass(frozen=True)
class StrategyConfig:
    """V3 신호 생성과 매매 판단에 사용하는 전략 설정 묶음입니다."""

    rsi_period: int = 14  # RSI를 계산할 종가 캔들의 개수입니다.
    trade: TradeConfig = field(default_factory=TradeConfig)  # RSI 신호에 따른 주문 판단 기준입니다.


@dataclass(frozen=True)
class SignalSnapshot:
    """완료된 최신 캔들에서 계산한 가격 및 RSI 신호값입니다."""

    rsi: float  # 최신 전략 캔들에서 계산한 RSI 값입니다.
    previous_rsi: float  # 최신 캔들 바로 이전의 RSI 값입니다.
    price: float  # 최신 전략 캔들의 종가(신호 판단 기준 가격)입니다.


@dataclass(frozen=True)
class TradeDecision:
    """순수 매매 판단의 결과와 주문에 사용할 수량 또는 금액입니다."""

    action: str  # ``BUY``, ``SELL_LOSS``, ``SELL_PROFIT``, ``WAIT`` 중 하나입니다.
    order_amount: float = 0.0  # 매수 시 원화 금액, 매도 시 코인 수량입니다.
    profit_rate: float = 0.0  # 매도 판단에 사용한 평균 매수가 대비 수익률(%)입니다.


def build_signal(
    ohlcv: pd.DataFrame,
    config: StrategyConfig = StrategyConfig(),
) -> SignalSnapshot:
    """완료된 OHLCV 캔들에서 V3의 RSI·이전 RSI·현재가를 계산합니다.

    Args:
        ohlcv: ``close`` 컬럼을 가진 시간순 OHLCV 데이터입니다. 마지막 행이
            신호를 계산할 최신 전략 캔들입니다.
        config: RSI 기간과 매매 기준을 가진 V3 전략 설정입니다.

    Returns:
        최신 RSI, 이전 RSI, 최신 종가를 담은 신호 스냅샷입니다.

    Raises:
        ValueError: RSI 기간·종가 컬럼·캔들 수가 유효하지 않을 때 발생합니다.
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
    krw_balance: float,
    coin_amount: float,
    avg_buy_price: float,
    current_price: float,
    config: TradeConfig = TradeConfig(),
) -> TradeDecision:
    """현재 RSI와 잔고를 바탕으로 V3의 다음 주문을 판단합니다.

    이 함수는 거래소 API를 호출하지 않으므로 단위 테스트와 실제 주문 실행에서
    같은 판단 규칙을 안전하게 공유할 수 있습니다.

    Args:
        rsi: 최신 전략 캔들에서 계산한 RSI 값입니다.
        krw_balance: 지금 주문에 사용할 수 있는 원화 잔고입니다.
        coin_amount: 현재 보유한 대상 코인의 수량입니다.
        avg_buy_price: 보유 코인의 평균 매수가입니다. 보유하지 않으면 ``0``입니다.
        current_price: 현재 신호가 기준으로 삼는 코인 가격입니다.
        config: 매수·매도 RSI, 익절률, 주문 비율을 담은 매매 설정입니다.

    Returns:
        다음 행동과 주문 금액 또는 수량을 담은 순수 판단 결과입니다.
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
