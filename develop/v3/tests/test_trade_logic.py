import unittest

from develop.v3.trade_logic import TradeConfig, decide_trade


class TradeLogicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = TradeConfig()

    # RSI가 매수 기준 이하고, 매수 비율을 적용한 금액이 최소 주문금액 이상이면 매수한다.
    def test_buys_when_rsi_is_oversold_and_minimum_order_is_met(self) -> None:
        decision = decide_trade(
            rsi=30.0,
            krw_balance=25_000.0,
            coin_amount=0.0,
            avg_buy_price=0.0,
            current_price=100.0,
            config=self.config,
        )

        self.assertEqual(decision.action, "BUY")
        self.assertEqual(decision.order_amount, 5_000.0)

    # RSI가 낮아도 매수 비율을 적용한 금액이 최소 주문금액보다 작으면 주문하지 않는다.
    def test_waits_when_buy_ratio_is_below_minimum_order(self) -> None:
        decision = decide_trade(
            rsi=25.0,
            krw_balance=24_999.0,
            coin_amount=0.0,
            avg_buy_price=0.0,
            current_price=100.0,
            config=self.config,
        )

        self.assertEqual(decision.action, "WAIT")

    # RSI가 매도 기준 이상이고 본전 또는 손실이면 보유 수량 전체를 매도한다.
    def test_sells_all_at_break_even_or_loss_when_rsi_is_overbought(self) -> None:
        decision = decide_trade(
            rsi=70.0,
            krw_balance=0.0,
            coin_amount=0.1,
            avg_buy_price=100.0,
            current_price=100.0,
            config=self.config,
        )

        self.assertEqual(decision.action, "SELL_LOSS")
        self.assertEqual(decision.order_amount, 0.1)
        self.assertEqual(decision.profit_rate, 0.0)

    # RSI가 매도 기준 이상이고 목표 수익률 5%에 도달하면 보유 수량 전체를 익절 매도한다.
    def test_sells_all_when_profit_target_is_met(self) -> None:
        decision = decide_trade(
            rsi=75.0,
            krw_balance=0.0,
            coin_amount=0.1,
            avg_buy_price=100.0,
            current_price=105.0,
            config=self.config,
        )

        self.assertEqual(decision.action, "SELL_PROFIT")
        self.assertEqual(decision.order_amount, 0.1)
        self.assertEqual(decision.profit_rate, 5.0)

    # RSI가 높아도 수익률이 본전 초과·목표 수익률 미만이면 보유 상태를 유지한다.
    def test_waits_for_profit_between_break_even_and_target(self) -> None:
        decision = decide_trade(
            rsi=75.0,
            krw_balance=0.0,
            coin_amount=0.1,
            avg_buy_price=100.0,
            current_price=103.0,
            config=self.config,
        )

        self.assertEqual(decision.action, "WAIT")
