"""V4 백테스트가 실제 V4 회복 진입 규칙을 사용하는지 검증합니다."""

import unittest
from dataclasses import replace

import pandas as pd

from develop.v4.backtesting.backtest_logic import run_backtest
from develop.v4.config import V4_CONFIG
from develop.v4.trade_logic import TradeConfig


class V4BacktestLogicTest(unittest.TestCase):
    """외부 API 없이 V4 순수 백테스트의 체결 흐름을 확인합니다."""

    # 하락 뒤 회복하는 합성 4시간봉에서는 V4가 회복 매수 후 RSI 청산을 만든다.
    def test_run_backtest_uses_recovery_buy_and_rsi_exit(self) -> None:
        """V4 백테스트가 V3의 단순 과매도 매수가 아닌 회복 진입 규칙을 쓰는지 확인합니다."""

        closes = [100, 99, 98, 97, 96, 95, 96, 98, 101, 105, 110, 115]
        ohlcv = pd.DataFrame(
            {"open": closes, "close": closes},
            index=pd.date_range("2026-01-01", periods=len(closes), freq="4h"),
        )
        config = replace(
            V4_CONFIG,
            strategy=replace(V4_CONFIG.strategy, rsi_period=2, trade=TradeConfig()),
            backtest=replace(V4_CONFIG.backtest, cron_interval_minutes=240),
        )

        result = run_backtest(ohlcv, config, pd.Timestamp("2026-01-01"))

        self.assertEqual([trade.action for trade in result.trades], ["BUY", "SELL_RSI"])
