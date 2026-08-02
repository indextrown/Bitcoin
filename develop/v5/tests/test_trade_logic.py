"""V5 반등 진입·목표가·손절·시간 청산의 순수 규칙을 검증합니다."""

import unittest

from develop.v5.trade_logic import (
    SignalSnapshot,
    StrategyConfig,
    TradeConfig,
    calculate_target_price,
    decide_entry,
    decide_exit,
)


class V5TradeLogicTest(unittest.TestCase):
    """거래소·파일 없이 실행되는 V5 단타 판단 테스트입니다."""

    def setUp(self) -> None:
        """각 테스트에서 공통으로 쓸 짧은 반등 전략 기준을 준비합니다."""

        self.config = StrategyConfig()

    # RSI와 가격이 모두 하단 밴드 하락 뒤 회복하면 배정 한도만 매수한다.
    def test_buys_only_for_rsi_and_lower_band_rebound_with_cap(self) -> None:
        """두 반등 조건과 V5 원화 한도가 신규 매수에 함께 적용되는지 확인합니다."""

        signal = SignalSnapshot(40.0, 39.0, 101.0, 95.0, 100.0, 96.0, 100.0)

        decision = decide_entry(signal, 1_000_000.0, 300_000.0, self.config)

        self.assertEqual(decision.action, "BUY")
        self.assertEqual(decision.order_amount, 300_000.0)

    # RSI만 회복하고 직전 종가가 하단 밴드 아래가 아니면 진입하지 않는다.
    def test_waits_when_lower_band_rebound_is_missing(self) -> None:
        """단순 RSI 반등으로 과도하게 진입하지 않는지 확인합니다."""

        signal = SignalSnapshot(40.0, 39.0, 101.0, 99.0, 100.0, 96.0, 100.0)

        decision = decide_entry(signal, 300_000.0, 300_000.0, self.config)

        self.assertEqual(decision.action, "WAIT")

    # 반등 신호가 있어도 현재가가 SMA(50) 아래면 하락 추세 진입을 막는다.
    def test_waits_when_price_is_below_trend_sma(self) -> None:
        """장기 추세 필터가 일시적인 하락 반등 매수를 차단하는지 확인합니다."""

        signal = SignalSnapshot(40.0, 39.0, 101.0, 95.0, 100.0, 96.0, 102.0)

        decision = decide_entry(signal, 300_000.0, 300_000.0, self.config)

        self.assertEqual(decision.action, "WAIT")

    # 수수료를 뺀 뒤에도 목표 순이익률이 남도록 호가 단위로 목표가를 올림한다.
    def test_target_price_covers_fee_and_requested_net_profit(self) -> None:
        """목표가가 매도 수수료 뒤에도 주문 원금의 0.1% 이상 남기는지 확인합니다."""

        target_price = calculate_target_price(100_000.0, 1.0, 0.0005, 0.1)

        self.assertEqual(target_price, 100_200.0)
        self.assertGreaterEqual(target_price * (1 - 0.0005) - 100_000.0, 100.0)

    # 진입가보다 1% 이상 하락하면 목표가 주문과 별개로 손절을 판단한다.
    def test_exits_at_configured_stop_loss(self) -> None:
        """현재가가 손절 가격 이하일 때 즉시 시장가 청산 판단을 내리는지 확인합니다."""

        decision = decide_exit(100_000.0, 99_000.0, 10.0, TradeConfig(stop_loss_pct=1.0))

        self.assertEqual(decision.action, "SELL_STOP_LOSS")
        self.assertEqual(decision.stop_price, 99_000.0)

    # 손절이 아니어도 최대 보유 시간이 지나면 포지션을 정리한다.
    def test_exits_when_maximum_holding_time_is_reached(self) -> None:
        """지정가 익절 미체결 포지션을 무기한 보유하지 않는지 확인합니다."""

        decision = decide_exit(100_000.0, 100_100.0, 90.0, TradeConfig(max_hold_minutes=90))

        self.assertEqual(decision.action, "SELL_TIME_EXIT")
