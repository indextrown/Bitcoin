"""V4·V5가 공유 원화 계좌에서 각자 예산 한도를 지키는지 검증합니다."""

import unittest

from develop.portfolio import calculate_order_budget


class PortfolioBudgetTest(unittest.TestCase):
    """실제 잔고와 전략별 한도의 작은 값을 주문 금액으로 쓰는지 확인합니다."""

    # 계좌에 100만원이 있어도 V5에 30만원만 배정하면 30만원을 초과하지 않는다.
    def test_limits_order_budget_to_strategy_cap(self) -> None:
        """독립 V5가 V4에 배정한 원화를 주문하지 않는지 확인합니다."""

        self.assertEqual(calculate_order_budget(1_000_000.0, 300_000.0), 300_000.0)

    # 다른 봇 주문 뒤 가용 원화가 줄면 한도보다 실제 잔고를 우선한다.
    def test_limits_order_budget_to_current_available_balance(self) -> None:
        """두 봇의 실행 순서가 달라도 잔고보다 큰 주문을 내지 않는지 확인합니다."""

        self.assertEqual(calculate_order_budget(250_000.0, 700_000.0), 250_000.0)
