"""V3 RSI 봇의 순수 매매 판단 로직입니다."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeConfig:
    buy_threshold: float = 30.0
    sell_threshold: float = 70.0
    sell_profit_pct: float = 5.0
    buy_ratio: float = 0.2
    min_trade_krw: float = 5_000.0


@dataclass(frozen=True)
class TradeDecision:
    action: str
    order_amount: float = 0.0
    profit_rate: float = 0.0


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
