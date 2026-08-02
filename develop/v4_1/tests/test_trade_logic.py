"""V4.1 추세 필터·손절 쿨다운·손익 청산 순수 함수를 검증합니다."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from develop.v4_1.trade_logic import SignalSnapshot, TradeConfig, decide_trade
from develop.v4_1.trade_state import TradeState, load_trade_state, save_trade_state


class V4_1TradeLogicTest(unittest.TestCase):
    """거래소·실제 파일 없이 실행되는 V4.1 매매 판단 테스트입니다."""

    def setUp(self) -> None:
        """각 테스트가 공통으로 사용할 판단 시각과 V4.1 기본 거래 기준을 준비합니다."""

        self.config = TradeConfig()
        self.decision_time = datetime(2026, 1, 10, 12, 0)

    def make_signal(
        self,
        rsi: float = 40.0,
        previous_rsi: float = 39.0,
        price: float = 110.0,
        trend_sma: float = 100.0,
        previous_trend_sma: float = 99.0,
    ) -> SignalSnapshot:
        """테스트마다 필요한 RSI 회복·추세 상태를 짧게 생성합니다.

        Args:
            rsi: 현재 전략 봉의 RSI입니다.
            previous_rsi: 직전 전략 봉의 RSI입니다.
            price: 현재 전략 봉 종가입니다.
            trend_sma: 현재 전략 봉까지 계산한 추세 이동평균입니다.
            previous_trend_sma: 직전 시점의 추세 이동평균입니다.

        Returns:
            지정한 값으로 만든 V4.1 순수 신호입니다.
        """

        return SignalSnapshot(rsi, previous_rsi, price, trend_sma, previous_trend_sma)

    # RSI 회복과 상승 추세가 모두 확인되면 가용 원화 전액을 매수한다.
    def test_buys_on_recovery_only_when_trend_is_up(self) -> None:
        """RSI 회복·상승 추세·쿨다운 종료가 함께 충족될 때만 매수하는지 확인합니다."""

        decision = decide_trade(
            self.make_signal(),
            1_000_000.0,
            0.0,
            0.0,
            self.decision_time,
            None,
            self.config,
        )

        self.assertEqual(decision.action, "BUY")
        self.assertEqual(decision.order_amount, 1_000_000.0)

    # RSI가 회복해도 가격이 하락 중인 이동평균 아래면 매수하지 않는다.
    def test_waits_when_recovery_has_no_uptrend_confirmation(self) -> None:
        """하락 추세의 일시적 RSI 반등을 추세 필터가 막는지 확인합니다."""

        decision = decide_trade(
            self.make_signal(price=98.0, trend_sma=100.0, previous_trend_sma=101.0),
            1_000_000.0,
            0.0,
            0.0,
            self.decision_time,
            None,
            self.config,
        )

        self.assertEqual(decision.action, "WAIT")

    # 손절 직후 24시간 안에는 새 RSI 회복 신호가 있어도 재진입하지 않는다.
    def test_waits_during_stop_loss_cooldown(self) -> None:
        """최근 손절 시각부터 설정한 쿨다운 시간이 지나기 전에는 매수하지 않는지 확인합니다."""

        decision = decide_trade(
            self.make_signal(),
            1_000_000.0,
            0.0,
            0.0,
            self.decision_time,
            datetime(2026, 1, 10, 1, 0),
            self.config,
        )

        self.assertEqual(decision.action, "WAIT")

    # 보유 중 손실률이 -10%에 닿으면 추세·쿨다운과 관계없이 먼저 손절한다.
    def test_sells_at_stop_loss_before_entry_filters(self) -> None:
        """보유 포지션의 위험 관리는 신규 매수 필터보다 우선하는지 확인합니다."""

        decision = decide_trade(
            self.make_signal(rsi=20.0, previous_rsi=19.0, price=90.0, trend_sma=100.0, previous_trend_sma=101.0),
            0.0,
            1.0,
            100.0,
            self.decision_time,
            None,
            self.config,
        )

        self.assertEqual(decision.action, "SELL_STOP_LOSS")
        self.assertEqual(decision.profit_rate, -10.0)

    # 손절 시각은 JSON 상태 파일에 저장했다가 다음 크론 실행에서 그대로 다시 읽는다.
    def test_persists_last_stop_loss_time(self) -> None:
        """프로세스가 종료돼도 손절 쿨다운이 사라지지 않도록 상태를 저장·복원하는지 확인합니다."""

        expected_time = datetime(2026, 1, 10, 12, 0)
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "trade_state.json"
            save_trade_state(state_path, TradeState(last_stop_loss_time=expected_time))
            state = load_trade_state(state_path)

        self.assertEqual(state.last_stop_loss_time, expected_time)
