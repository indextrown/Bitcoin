import importlib.util
import importlib
from dataclasses import asdict
import pathlib
import sys
import unittest
from unittest.mock import patch

import pandas as pd


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

V0_1_PATH = ROOT_DIR / "operate" / "v0-1" / "strategy_v0_1.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


strategy_v0 = importlib.import_module("operate.v0.strategy_v0")
strategy_v0_1 = load_module("strategy_v0_1_for_test", V0_1_PATH)


class StrategyV01Test(unittest.TestCase):
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

    def test_calculate_order_budget_matches_v0(self):
        config = strategy_v0_1.StrategyConfig(buy_ratio=0.2, min_trade_krw=5000)

        self.assertEqual(
            strategy_v0.calculate_order_budget(50000, config),
            strategy_v0_1.calculate_order_budget(50000, config),
        )

    def test_build_v0_1_signal_matches_v0_logic(self):
        balances = [{"currency": "KRW", "balance": "100000", "locked": "0", "avg_buy_price": "0", "unit_currency": "KRW"}]
        snapshot_v0 = strategy_v0.SignalSnapshot("KRW-ETH", 100.0, 28.0, 31.0)
        snapshot_v0_1 = strategy_v0_1.SignalSnapshot("KRW-ETH", 100.0, 28.0, 31.0)

        with patch.object(strategy_v0, "get_ohlcv", return_value=self.make_df()):
            with patch.object(strategy_v0, "build_snapshot", return_value=snapshot_v0):
                expected = strategy_v0.build_v0_signal(balances, 100000)

        with patch.object(strategy_v0_1, "get_ohlcv", return_value=self.make_df()):
            with patch.object(strategy_v0_1, "build_snapshot", return_value=snapshot_v0_1):
                actual = strategy_v0_1.build_v0_1_signal(balances, 100000)

        self.assertEqual(expected["holding"], actual["holding"])
        self.assertEqual(asdict(expected["entry_signal"]), asdict(actual["entry_signal"]))
        self.assertEqual(expected["exit_signal"], actual["exit_signal"])


if __name__ == "__main__":
    unittest.main()
