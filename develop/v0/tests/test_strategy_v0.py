import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

import pandas as pd


ROOT_DIR = pathlib.Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT_DIR / "develop" / "v0" / "strategy_v0.py"


def load_module():
    spec = importlib.util.spec_from_file_location("strategy_v0", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


strategy = load_module()


class StrategyV0Test(unittest.TestCase):
    def make_df(self):
        return pd.DataFrame(
            {
                "close": [
                    120, 119, 118, 117, 116, 115, 114, 113, 112, 111,
                    110, 109, 108, 107, 106, 105, 104, 103, 102, 101,
                    100, 99, 98, 97, 98, 99, 100,
                ]
            }
        )

    def test_calculate_order_budget_applies_min_trade(self):
        config = strategy.StrategyConfig(buy_ratio=0.2, min_trade_krw=5000)
        self.assertEqual(strategy.calculate_order_budget(10000, config), 0.0)
        self.assertEqual(strategy.calculate_order_budget(50000, config), 10000.0)

    def test_evaluate_entry_signal_returns_buy_signal(self):
        snapshot = strategy.SignalSnapshot("KRW-ETH", 100.0, 28.0, 31.0)

        result = strategy.evaluate_entry_signal(snapshot, 100000, False)

        self.assertTrue(result.should_buy)
        self.assertEqual(result.reason, "buy_signal")

    def test_evaluate_entry_signal_blocks_when_already_holding(self):
        snapshot = strategy.SignalSnapshot("KRW-ETH", 100.0, 28.0, 31.0)

        result = strategy.evaluate_entry_signal(snapshot, 100000, True)

        self.assertFalse(result.should_buy)
        self.assertEqual(result.reason, "already_holding")

    def test_evaluate_exit_signal_returns_take_profit(self):
        snapshot = strategy.SignalSnapshot("KRW-ETH", 130.0, 75.0, 72.0)
        balances = [{"currency": "ETH", "balance": "0.2", "locked": "0", "avg_buy_price": "100", "unit_currency": "KRW"}]

        with patch.object(strategy, "get_revenue_rate", return_value=6.5):
            result = strategy.evaluate_exit_signal(snapshot, balances)

        self.assertTrue(result.should_sell)
        self.assertEqual(result.reason, "take_profit")

    def test_evaluate_exit_signal_returns_flat_or_loss_exit(self):
        snapshot = strategy.SignalSnapshot("KRW-ETH", 100.0, 74.0, 72.0)
        balances = [{"currency": "ETH", "balance": "0.2", "locked": "0", "avg_buy_price": "100", "unit_currency": "KRW"}]

        with patch.object(strategy, "get_revenue_rate", return_value=-0.5):
            result = strategy.evaluate_exit_signal(snapshot, balances)

        self.assertTrue(result.should_sell)
        self.assertEqual(result.reason, "flat_or_loss_exit")

    def test_build_v0_signal_returns_entry_when_not_holding(self):
        balances = [{"currency": "KRW", "balance": "100000", "locked": "0", "avg_buy_price": "0", "unit_currency": "KRW"}]

        with patch.object(strategy, "get_ohlcv", return_value=self.make_df()):
            with patch.object(strategy, "build_snapshot", return_value=strategy.SignalSnapshot("KRW-ETH", 100.0, 28.0, 31.0)):
                result = strategy.build_v0_signal(balances, 100000)

        self.assertFalse(result["holding"])
        self.assertTrue(result["entry_signal"].should_buy)
        self.assertIsNone(result["exit_signal"])


if __name__ == "__main__":
    unittest.main()
