import unittest

import pandas as pd

from develop.v3.backtesting.backtest_visualizer import run_backtest, validate_ohlcv


class V3BacktestVisualizerTest(unittest.TestCase):
    def make_ohlcv(self, closes: list[float]) -> pd.DataFrame:
        index = pd.date_range("2025-01-01", periods=len(closes), freq="4h")
        return pd.DataFrame(
            {
                "open": closes,
                "close": closes,
            },
            index=index,
        )

    # 백테스트에 필요한 시가 또는 종가가 없으면 명확한 오류를 낸다.
    def test_validate_ohlcv_requires_open_and_close_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "open"):
            validate_ohlcv(pd.DataFrame({"close": [100.0] * 16}))

    # 하락 추세에서 RSI가 매수 기준에 도달하면 다음 캔들 시가에 매수 체결한다.
    def test_run_backtest_records_buy_at_next_candle_open(self) -> None:
        result = run_backtest(self.make_ohlcv([200.0 - index for index in range(20)]))

        first_trade = result.trades[0]
        self.assertEqual(first_trade.action, "BUY")
        self.assertGreater(first_trade.execution_time, first_trade.signal_time)

    # 매수 뒤 상승 추세가 이어져 RSI와 목표 수익률을 모두 충족하면 익절 매도한다.
    def test_run_backtest_records_profit_sell(self) -> None:
        closes = [200.0 - index for index in range(18)] + [183.0 + index * 5 for index in range(18)]
        result = run_backtest(self.make_ohlcv(closes))

        actions = [trade.action for trade in result.trades]
        self.assertIn("BUY", actions)
        self.assertIn("SELL_PROFIT", actions)
