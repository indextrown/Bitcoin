"""V5 시장가 매수·지정가 매도 사이 주문 상태 저장을 검증합니다."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from develop.v5.trade_state import ScalpState, load_trade_state, save_trade_state


class V5TradeStateTest(unittest.TestCase):
    """V5 상태 파일을 다시 읽어도 주문 진행 정보가 유지되는지 확인합니다."""

    # 목표가 주문이 열려 있는 상태를 저장하고 다시 읽으면 모든 핵심 값이 남아 있어야 한다.
    def test_round_trips_open_target_order_state(self) -> None:
        """독립 크론 실행 사이에 목표가·진입 정보가 손실되지 않는지 확인합니다."""

        with TemporaryDirectory() as directory:
            path = Path(directory) / "trade_state.json"
            state = ScalpState(
                status="TARGET_OPEN",
                entry_order_uuid="entry-uuid",
                entry_cost_krw=300_000.0,
                entry_time=datetime(2026, 8, 3, 10, 0),
                acquired_volume=0.003,
                entry_price=100_000_000.0,
                target_order_uuid="target-uuid",
                target_price=100_300_000.0,
            )

            save_trade_state(path, state)
            restored = load_trade_state(path)

        self.assertEqual(restored, state)
