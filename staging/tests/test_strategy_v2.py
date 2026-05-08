import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

import pandas as pd


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "operate" / "v2" / "strategy_v2.py"


def load_module():
    spec = importlib.util.spec_from_file_location("strategy_v2", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


strategy = load_module()


class StrategyV2Test(unittest.TestCase):
    def make_trend_df(self):
        rows = []
        price = 100.0
        for _ in range(80):
            rows.append(
                {
                    "open": price - 1.0,
                    "high": price + 2.0,
                    "low": price - 2.0,
                    "close": price,
                    "volume": 1000.0,
                }
            )
            price += 1.2
        return pd.DataFrame(rows)

    def make_signal_df_for_entry(self):
        closes = [
            100, 99, 98, 97, 96, 95, 94, 95, 96, 97,
            98, 99, 100, 101, 102, 103, 104, 105, 106, 107,
            108, 109, 110, 111, 112, 113, 114, 115, 116, 125,
        ]
        rows = []
        for idx, close in enumerate(closes):
            high = close + 2.0
            if idx == len(closes) - 2:
                high = close + 6.0
            if idx == len(closes) - 1:
                high = close + 8.0
            rows.append(
                {
                    "open": close - 1.0,
                    "high": high,
                    "low": close - 2.0,
                    "close": close,
                    "volume": 1000.0 if idx < len(closes) - 1 else 2200.0,
                }
            )
        return pd.DataFrame(rows)

    def make_signal_df_for_downtrend(self):
        rows = []
        price = 130.0
        for _ in range(30):
            rows.append(
                {
                    "open": price + 0.5,
                    "high": price + 1.0,
                    "low": price - 2.0,
                    "close": price,
                    "volume": 1200.0,
                }
            )
            price -= 1.0
        return pd.DataFrame(rows)

    def test_evaluate_entry_signal_returns_buy_signal(self):
        signal = strategy.evaluate_entry_signal(
            "KRW-BTC",
            self.make_trend_df(),
            self.make_signal_df_for_entry(),
        )

        self.assertTrue(signal.should_buy)
        self.assertEqual(signal.reason, "buy_signal")
        self.assertGreater(signal.volume_ratio, 1.3)

    def test_evaluate_entry_signal_blocks_when_volume_is_not_confirmed(self):
        signal_df = self.make_signal_df_for_entry()
        signal_df.loc[signal_df.index[-1], "volume"] = 1100.0

        signal = strategy.evaluate_entry_signal(
            "KRW-BTC",
            self.make_trend_df(),
            signal_df,
        )

        self.assertFalse(signal.should_buy)
        self.assertEqual(signal.reason, "volume_not_confirmed")

    def test_evaluate_exit_signal_returns_stop_loss(self):
        balances = [{"currency": "BTC", "balance": "0.01", "locked": "0", "avg_buy_price": "100", "unit_currency": "KRW"}]

        with patch.object(strategy, "get_revenue_rate", return_value=-5.0):
            signal = strategy.evaluate_exit_signal(
                "KRW-BTC",
                balances,
                self.make_signal_df_for_entry(),
            )

        self.assertTrue(signal.should_sell)
        self.assertEqual(signal.reason, "stop_loss")

    def test_evaluate_exit_signal_returns_trend_breakdown(self):
        balances = [{"currency": "BTC", "balance": "0.01", "locked": "0", "avg_buy_price": "100", "unit_currency": "KRW"}]

        with patch.object(strategy, "get_revenue_rate", return_value=1.0):
            signal = strategy.evaluate_exit_signal(
                "KRW-BTC",
                balances,
                self.make_signal_df_for_downtrend(),
            )

        self.assertTrue(signal.should_sell)
        self.assertEqual(signal.reason, "trend_breakdown")

    def test_calculate_order_budget_respects_allocation_cap(self):
        config = strategy.StrategyConfig(allocation_ratio=0.2, risk_per_trade_ratio=0.05, min_trade_krw=5000)
        budget = strategy.calculate_order_budget(100000, self.make_signal_df_for_entry(), config)
        self.assertGreater(budget, 0.0)
        self.assertLessEqual(budget, 20000.0)

    def test_build_v2_signals_collects_buy_and_sell_candidates(self):
        balances = [
            {"currency": "KRW", "balance": "100000", "locked": "0", "avg_buy_price": "0", "unit_currency": "KRW"},
            {"currency": "ETH", "balance": "0.2", "locked": "0", "avg_buy_price": "4000000", "unit_currency": "KRW"},
        ]

        signal_map = {
            ("KRW-BTC", "day"): self.make_trend_df(),
            ("KRW-BTC", "minute240"): self.make_signal_df_for_entry(),
            ("KRW-ETH", "minute240"): self.make_signal_df_for_downtrend(),
        }

        def fake_get_ohlcv(ticker, interval="day", count=200):
            return signal_map[(ticker, interval)]

        with patch.object(strategy, "get_top_coin_list", return_value=["KRW-BTC", "KRW-ETH"]):
            with patch.object(strategy, "get_ohlcv", side_effect=fake_get_ohlcv):
                with patch.object(strategy, "get_revenue_rate", return_value=1.0):
                    result = strategy.build_v2_signals(balances, krw_balance=100000)

        self.assertEqual(len(result["buy_signals"]), 1)
        self.assertEqual(result["buy_signals"][0].ticker, "KRW-BTC")
        self.assertEqual(len(result["sell_signals"]), 1)
        self.assertEqual(result["sell_signals"][0].ticker, "KRW-ETH")


if __name__ == "__main__":
    unittest.main()
