"""V5 백테스트의 다음 봉 진입과 목표가 체결 가정을 검증합니다."""

from dataclasses import replace
import unittest
from unittest.mock import patch

import pandas as pd

from develop.v5.backtesting.backtest_logic import run_backtest
from develop.v5.config import V5_CONFIG
from develop.v5.trade_logic import StrategyConfig, TradeConfig


class V5BacktestLogicTest(unittest.TestCase):
    """거래소 호출 없이 V5 단타 체결 순서를 확인합니다."""

    # 완료된 첫 봉 신호는 다음 5분봉 시가에 매수되고, 그 봉 고가가 목표가를 넘으면 매도된다.
    def test_executes_entry_on_next_candle_and_fills_target(self) -> None:
        """신호 봉의 미래 고가를 매수 가격에 쓰지 않고 목표가 체결은 이후 봉에서만 보는지 확인합니다."""

        index = pd.date_range("2026-08-01 00:00", periods=4, freq="5min")
        ohlcv = pd.DataFrame(
            {
                "open": [100_000.0, 100_000.0, 100_000.0, 100_000.0],
                "high": [100_100.0, 100_100.0, 100_500.0, 100_100.0],
                "low": [99_900.0, 99_900.0, 99_900.0, 99_900.0],
                "close": [100_000.0, 100_000.0, 100_000.0, 100_000.0],
            },
            index=index,
        )
        config = replace(
            V5_CONFIG,
            strategy=StrategyConfig(trade=TradeConfig(target_net_profit_pct=0.1, max_hold_minutes=90)),
        )
        signal_frame = pd.DataFrame(
            {
                "rsi": [39.0, 40.0, 40.0, 40.0],
                "price": [99_000.0, 100_000.0, 100_000.0, 100_000.0],
                "lower_band": [99_500.0, 99_500.0, 99_500.0, 99_500.0],
                "trend_sma": [99_900.0, 99_900.0, 99_900.0, 99_900.0],
            },
            index=index,
        )

        with patch("develop.v5.backtesting.backtest_logic.calculate_signal_frame", return_value=signal_frame):
            result = run_backtest(ohlcv, config)

        self.assertEqual(result.trades[0].action, "BUY")
        self.assertEqual(result.trades[0].execution_time, index[2])
        self.assertEqual(result.trades[1].action, "SELL_TARGET")
        self.assertEqual(result.trades[1].execution_time, index[2] + pd.Timedelta(minutes=5))
