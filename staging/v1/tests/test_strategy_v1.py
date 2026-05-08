import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

import pandas as pd


ROOT_DIR = pathlib.Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT_DIR / "staging" / "v1" / "strategy_v1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("strategy_v1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


strategy = load_module()


class StrategyV1Test(unittest.TestCase):
    def make_trend_df(self):
        return pd.DataFrame(
            {
                "close": [
                    100,
                    101,
                    102,
                    103,
                    104,
                    105,
                    106,
                    107,
                    108,
                    109,
                    110,
                    111,
                    112,
                    113,
                    114,
                    115,
                    116,
                    117,
                    118,
                    119,
                    120,
                    121,
                ]
            }
        )

    def make_signal_df(self):
        return pd.DataFrame(
            {
                "close": [
                    120,
                    119,
                    118,
                    117,
                    116,
                    115,
                    114,
                    113,
                    112,
                    111,
                    110,
                    109,
                    108,
                    107,
                    106,
                    105,
                    104,
                    103,
                    102,
                    101,
                    100,
                    99,
                    100,
                    103,
                    106,
                ]
            }
        )

    def make_downtrend_signal_df(self):
        return pd.DataFrame(
            {
                "close": [
                    130,
                    129,
                    128,
                    127,
                    126,
                    125,
                    124,
                    123,
                    122,
                    121,
                    120,
                    119,
                    118,
                    117,
                    116,
                    115,
                    114,
                    113,
                    112,
                    111,
                    110,
                    109,
                    108,
                    107,
                    106,
                ]
            }
        )

    def test_evaluate_entry_signal_returns_buy_signal(self):
        signal = strategy.evaluate_entry_signal(
            "KRW-BTC",
            self.make_trend_df(),
            self.make_signal_df(),
        )

        self.assertTrue(signal.should_buy)
        self.assertEqual(signal.reason, "buy_signal")

    def test_evaluate_entry_signal_blocks_when_trend_is_not_bullish(self):
        downtrend_df = self.make_downtrend_signal_df()

        signal = strategy.evaluate_entry_signal(
            "KRW-BTC",
            downtrend_df,
            self.make_signal_df(),
        )

        self.assertFalse(signal.should_buy)
        self.assertEqual(signal.reason, "trend_not_bullish")

    def test_evaluate_exit_signal_returns_stop_loss(self):
        balances = [{"currency": "BTC", "balance": "0.01", "locked": "0", "avg_buy_price": "100", "unit_currency": "KRW"}]

        with patch.object(strategy, "get_revenue_rate", return_value=-4.2):
            signal = strategy.evaluate_exit_signal(
                "KRW-BTC",
                balances,
                self.make_signal_df(),
            )

        self.assertTrue(signal.should_sell)
        self.assertEqual(signal.reason, "stop_loss")

    def test_evaluate_exit_signal_returns_trend_breakdown(self):
        balances = [{"currency": "BTC", "balance": "0.01", "locked": "0", "avg_buy_price": "100", "unit_currency": "KRW"}]

        with patch.object(strategy, "get_revenue_rate", return_value=1.0):
            signal = strategy.evaluate_exit_signal(
                "KRW-BTC",
                balances,
                self.make_downtrend_signal_df(),
            )

        self.assertTrue(signal.should_sell)
        self.assertEqual(signal.reason, "trend_breakdown")

    def test_calculate_order_budget_applies_min_trade(self):
        config = strategy.StrategyConfig(allocation_ratio=0.2, min_trade_krw=5000)
        self.assertEqual(strategy.calculate_order_budget(10000, config), 0.0)
        self.assertEqual(strategy.calculate_order_budget(50000, config), 10000.0)

    def test_build_v1_signals_collects_buy_and_sell_candidates(self):
        balances = [
            {"currency": "KRW", "balance": "100000", "locked": "0", "avg_buy_price": "0", "unit_currency": "KRW"},
            {"currency": "ETH", "balance": "0.2", "locked": "0", "avg_buy_price": "4000000", "unit_currency": "KRW"},
        ]

        signal_map = {
            ("KRW-BTC", "day"): self.make_trend_df(),
            ("KRW-BTC", "minute60"): self.make_signal_df(),
            ("KRW-ETH", "minute60"): self.make_downtrend_signal_df(),
        }

        def fake_get_ohlcv(ticker, interval="day", count=200):
            return signal_map[(ticker, interval)]

        with patch.object(strategy, "get_top_coin_list", return_value=["KRW-BTC", "KRW-ETH"]):
            with patch.object(strategy, "get_ohlcv", side_effect=fake_get_ohlcv):
                with patch.object(strategy, "get_revenue_rate", return_value=1.5):
                    result = strategy.build_v1_signals(balances, krw_balance=100000)

        self.assertEqual(len(result["buy_signals"]), 1)
        self.assertEqual(result["buy_signals"][0].ticker, "KRW-BTC")
        self.assertEqual(len(result["sell_signals"]), 1)
        self.assertEqual(result["sell_signals"][0].ticker, "KRW-ETH")


if __name__ == "__main__":
    unittest.main()
