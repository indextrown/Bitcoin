import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "operate" / "backtest_v1_v2.py"


def load_module():
    spec = importlib.util.spec_from_file_location("backtest_v1_v2", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


backtest = load_module()


class BacktestV1V2Test(unittest.TestCase):
    def test_build_balance_row_creates_upbit_like_balance(self):
        balances = backtest.build_balance_row("KRW-BTC", 0.01, 100000000)

        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0]["currency"], "BTC")
        self.assertEqual(balances[0]["unit_currency"], "KRW")

    def test_compute_max_drawdown_pct_returns_negative_drawdown(self):
        equity_curve = pd.Series([100, 110, 105, 90, 95])

        value = backtest.compute_max_drawdown_pct(equity_curve)

        self.assertAlmostEqual(value, -18.1818181818, places=5)

    def test_compute_win_rate_pct_counts_closed_wins_only(self):
        trades = [
            backtest.Trade("buy", pd.Timestamp("2025-01-01"), 100.0, 1.0, "buy_signal", 1000.0),
            backtest.Trade("sell", pd.Timestamp("2025-01-02"), 110.0, 1.0, "take_profit", 1100.0),
            backtest.Trade("buy", pd.Timestamp("2025-01-03"), 120.0, 1.0, "buy_signal", 1100.0),
            backtest.Trade("sell", pd.Timestamp("2025-01-04"), 115.0, 1.0, "stop_loss", 1050.0),
        ]

        value = backtest.compute_win_rate_pct(trades)

        self.assertEqual(value, 50.0)

    def test_validate_data_rejects_missing_signal_columns(self):
        day_df = pd.DataFrame({"close": [1, 2, 3]})
        signal_df = pd.DataFrame({"close": [1, 2, 3]})

        with self.assertRaises(ValueError):
            backtest.validate_data(day_df, signal_df)


if __name__ == "__main__":
    unittest.main()
