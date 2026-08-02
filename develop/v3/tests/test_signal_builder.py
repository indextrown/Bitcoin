import unittest

import pandas as pd

from develop.v3.trade_logic import StrategyConfig, build_signal


class SignalBuilderTest(unittest.TestCase):
    """공용 설정을 사용한 RSI 신호 생성 함수를 검증합니다."""

    # RSI 기간을 바꾸면 같은 순수 함수가 해당 기간으로 현재 신호를 계산한다.
    def test_build_signal_uses_configured_rsi_period(self) -> None:
        """설정한 RSI 기간으로 최신 RSI·이전 RSI·종가를 계산하는지 확인합니다."""

        ohlcv = pd.DataFrame({"close": [100.0 - index for index in range(8)]})
        signal = build_signal(ohlcv, StrategyConfig(rsi_period=2))

        self.assertEqual(signal.rsi, 0.0)
        self.assertEqual(signal.previous_rsi, 0.0)
        self.assertEqual(signal.price, 93.0)
