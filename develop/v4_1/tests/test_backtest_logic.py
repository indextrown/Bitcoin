"""V4.1 백테스트가 추세 필터가 붙은 RSI 회복 진입을 재사용하는지 검증합니다."""

from dataclasses import replace
import unittest

import pandas as pd

from develop.v4_1.backtesting.backtest_logic import run_backtest
from develop.v4_1.config import V4_1_CONFIG
from develop.v4_1.trade_logic import TradeConfig


class V4_1BacktestLogicTest(unittest.TestCase):
    """외부 API 없이 V4.1 순수 백테스트의 체결 흐름을 확인합니다."""

    # 하락 후 회복하며 상승 추세가 확인된 합성 4시간봉에서는 매수 후 RSI 청산을 만든다.
    def test_run_backtest_uses_trend_confirmed_recovery_buy_and_rsi_exit(self) -> None:
        """백테스터가 실거래와 같은 V4.1 RSI 회복·추세 필터 판단을 쓰는지 확인합니다."""

        closes = [100, 105, 110, 90, 80, 85, 100, 110, 115, 120]
        ohlcv = pd.DataFrame(
            {"open": closes, "close": closes},
            index=pd.date_range("2026-01-01", periods=len(closes), freq="4h"),
        )
        config = replace(
            V4_1_CONFIG,
            strategy=replace(
                V4_1_CONFIG.strategy,
                rsi_period=2,
                trade=TradeConfig(
                    trend_sma_period=3,
                    take_profit_pct=100.0,
                    stop_loss_pct=100.0,
                ),
            ),
            backtest=replace(V4_1_CONFIG.backtest, cron_interval_minutes=240),
        )

        result = run_backtest(ohlcv, config, pd.Timestamp("2026-01-01"))

        self.assertEqual([trade.action for trade in result.trades], ["BUY", "SELL_RSI"])
