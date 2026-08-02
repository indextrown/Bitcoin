"""V4 RSI 회복 진입·익절·손절·RSI 청산 규칙을 검증합니다."""

import unittest

from develop.v4.trade_logic import TradeConfig, decide_trade


class V4TradeLogicTest(unittest.TestCase):
    """거래소·파일 없이 실행되는 V4 순수 매매 판단 테스트입니다."""

    def setUp(self) -> None:
        """각 테스트가 공통으로 사용할 V4 거래 기준을 준비합니다."""

        self.config = TradeConfig()

    # RSI가 40 아래에서 위로 회복하고 현금이 있으면 전액 매수한다.
    def test_buys_only_when_rsi_recovers_above_buy_threshold(self) -> None:
        """과매도 상태 자체가 아니라 과매도 탈출 순간에만 매수하는지 확인합니다."""

        decision = decide_trade(40.0, 39.0, 1_000_000.0, 0.0, 0.0, 3_000_000.0, self.config)

        self.assertEqual(decision.action, "BUY")
        self.assertEqual(decision.order_amount, 1_000_000.0)

    # 공유 계좌에 원화가 더 있어도 V4 신규 매수는 포트폴리오 한도를 넘지 않는다.
    def test_limits_buy_to_shared_portfolio_cap(self) -> None:
        """V5와 독립 실행해도 V4가 배정받은 원화만 새 진입에 쓰는지 확인합니다."""

        decision = decide_trade(
            40.0,
            39.0,
            1_000_000.0,
            0.0,
            0.0,
            3_000_000.0,
            self.config,
            max_order_krw=700_000.0,
        )

        self.assertEqual(decision.action, "BUY")
        self.assertEqual(decision.order_amount, 700_000.0)

    # RSI가 계속 낮아도 회복 교차가 아니면 하락 중 반복 매수하지 않는다.
    def test_waits_while_rsi_remains_below_buy_threshold(self) -> None:
        """이전·현재 RSI가 모두 매수 기준 아래면 대기하는지 확인합니다."""

        decision = decide_trade(30.0, 25.0, 1_000_000.0, 0.0, 0.0, 3_000_000.0, self.config)

        self.assertEqual(decision.action, "WAIT")

    # 평균 매수가보다 10% 하락하면 RSI와 무관하게 손절한다.
    def test_sells_at_configured_stop_loss(self) -> None:
        """손실률이 -10%에 도달하면 손절 매도하는지 확인합니다."""

        decision = decide_trade(35.0, 34.0, 0.0, 1.0, 100.0, 90.0, self.config)

        self.assertEqual(decision.action, "SELL_STOP_LOSS")
        self.assertEqual(decision.profit_rate, -10.0)

    # 평균 매수가보다 3% 상승하면 RSI 과매수 전에도 익절한다.
    def test_sells_at_configured_take_profit(self) -> None:
        """수익률이 +3%에 도달하면 익절 매도하는지 확인합니다."""

        decision = decide_trade(60.0, 55.0, 0.0, 1.0, 100.0, 103.0, self.config)

        self.assertEqual(decision.action, "SELL_TAKE_PROFIT")
        self.assertEqual(decision.profit_rate, 3.0)

    # 손절·익절에 닿지 않아도 RSI 75 이상이면 전량 청산한다.
    def test_sells_when_rsi_reaches_sell_threshold(self) -> None:
        """보유 중 RSI가 매도 기준 이상이면 RSI 청산하는지 확인합니다."""

        decision = decide_trade(75.0, 70.0, 0.0, 1.0, 100.0, 101.0, self.config)

        self.assertEqual(decision.action, "SELL_RSI")
