"""서로 다른 티커를 거래하는 독립 봇의 원화 주문 한도를 계산합니다."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioConfig:
    """공유 업비트 원화 계좌에서 전략별로 사용할 최대 매수 예산입니다."""

    v4_max_capital_krw: float = 700_000.0  # ETH 전용 V4가 한 번의 신규 진입에 사용할 최대 원화입니다.
    v5_max_capital_krw: float = 300_000.0  # ETH 이외 단일 티커 V5가 한 번의 신규 진입에 사용할 최대 원화입니다.


PORTFOLIO_CONFIG = PortfolioConfig()


def calculate_order_budget(available_krw: float, strategy_max_capital_krw: float) -> float:
    """현재 계좌 원화와 전략 예산 한도 중 작은 값을 주문 예산으로 반환합니다.

    Args:
        available_krw: 주문 직전에 업비트에서 조회한 실제 가용 원화 잔고입니다.
        strategy_max_capital_krw: 해당 전략이 한 번의 신규 진입에 사용할 최대 원화입니다.

    Returns:
        다른 전략의 예산을 침범하지 않는 이번 주문의 최대 원화 금액입니다.

    Raises:
        ValueError: 예산 한도가 음수일 때 발생합니다.
    """

    if strategy_max_capital_krw < 0:
        raise ValueError("strategy_max_capital_krw must not be negative.")
    return max(0.0, min(available_krw, strategy_max_capital_krw))
