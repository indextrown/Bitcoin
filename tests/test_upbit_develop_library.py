import importlib.util
import pathlib
import unittest
from unittest.mock import patch

import pandas as pd


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "develop" / "upbit_develop_library.py"


def load_module():
    spec = importlib.util.spec_from_file_location("upbit_develop_library", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


lib = load_module()


class UpbitDevelopLibraryTest(unittest.TestCase):
    def setUp(self):
        """여러 테스트에서 공통으로 사용할 샘플 차트/잔고 데이터를 준비합니다."""

        self.sample_ohlcv = pd.DataFrame(
            {
                "close": [
                    100,
                    102,
                    101,
                    105,
                    107,
                    106,
                    108,
                    110,
                    109,
                    111,
                    113,
                    112,
                    115,
                    117,
                    116,
                    118,
                    120,
                    121,
                    119,
                    122,
                ]
            }
        )
        self.sample_balances = [
            {
                "currency": "KRW",
                "balance": "500000",
                "locked": "10000",
                "avg_buy_price": "0",
                "unit_currency": "KRW",
            },
            {
                "currency": "BTC",
                "balance": "0.01",
                "locked": "0.005",
                "avg_buy_price": "90000000",
                "unit_currency": "KRW",
            },
            {
                "currency": "ETH",
                "balance": "0.2",
                "locked": "0",
                "avg_buy_price": "4000000",
                "unit_currency": "KRW",
            },
            {
                "currency": "APENFT",
                "balance": "100",
                "locked": "0",
                "avg_buy_price": "0",
                "unit_currency": "KRW",
            },
        ]

    def test_compose_balance_ticker(self):
        """잔고 한 줄 데이터가 KRW-BTC 형태의 티커 문자열로 조합되는지 확인합니다."""

        ticker = lib._compose_balance_ticker(self.sample_balances[1])
        self.assertEqual(ticker, "KRW-BTC")

    def test_build_balance_map(self):
        """잔고 목록이 티커 기준 딕셔너리로 변환되는지 확인합니다."""

        balance_map = lib.build_balance_map(self.sample_balances)
        self.assertIn("KRW-BTC", balance_map)
        self.assertIn("KRW-ETH", balance_map)
        self.assertEqual(balance_map["KRW-BTC"]["currency"], "BTC")

    def test_is_ticker_in_list(self):
        """티커 목록 안에 특정 티커가 있는지 올바르게 판별하는지 확인합니다."""

        tickers = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
        self.assertTrue(lib.is_ticker_in_list(tickers, "KRW-ETH"))
        self.assertFalse(lib.is_ticker_in_list(tickers, "KRW-DOGE"))

    def test_is_ticker_in_set(self):
        """set 형태로 넘겨도 티커 포함 여부를 올바르게 판별하는지 확인합니다."""

        tickers = {"KRW-BTC", "KRW-ETH", "KRW-XRP"}
        self.assertTrue(lib.is_ticker_in_list(tickers, "KRW-BTC"))
        self.assertFalse(lib.is_ticker_in_list(tickers, "KRW-SOL"))

    def test_calculate_rsi_series_returns_series(self):
        """RSI 시리즈 계산 결과가 같은 길이의 pandas Series로 반환되는지 확인합니다."""

        rsi_series = lib.calculate_rsi_series(self.sample_ohlcv, period=14)
        self.assertEqual(rsi_series.name, "RSI")
        self.assertEqual(len(rsi_series), len(self.sample_ohlcv))
        self.assertTrue(rsi_series.iloc[-1] > 0)

    def test_get_rsi_matches_series_value(self):
        """단일 RSI 조회값이 RSI 시리즈의 같은 위치 값과 일치하는지 확인합니다."""

        expected = float(lib.calculate_rsi_series(self.sample_ohlcv, period=14).iloc[-1])
        actual = lib.get_rsi(self.sample_ohlcv, period=14, st=-1)
        self.assertAlmostEqual(actual, expected, places=8)

    def test_get_moving_average(self):
        """이동평균선 계산값이 pandas rolling 평균 결과와 일치하는지 확인합니다."""

        actual = lib.get_moving_average(self.sample_ohlcv, period=5, st=-1)
        expected = float(self.sample_ohlcv["close"].rolling(5).mean().iloc[-1])
        self.assertAlmostEqual(actual, expected, places=8)

    def test_has_coin(self):
        """잔고 목록에 코인이 있을 때와 없을 때를 정확히 구분하는지 확인합니다."""

        self.assertTrue(lib.has_coin(self.sample_balances, "KRW-BTC"))
        self.assertFalse(lib.has_coin(self.sample_balances, "KRW-XRP"))

    def test_has_coin_with_balance_map(self):
        """잔고 딕셔너리를 넘겨도 보유 여부를 올바르게 확인하는지 검증합니다."""

        balance_map = lib.build_balance_map(self.sample_balances)
        self.assertTrue(lib.has_coin(balance_map, "KRW-ETH"))
        self.assertFalse(lib.has_coin(balance_map, "KRW-SOL"))

    def test_get_coin_now_money_includes_locked(self):
        """총 매수 금액 계산에 locked 수량까지 포함되는지 확인합니다."""

        actual = lib.get_coin_now_money(self.sample_balances, "KRW-BTC")
        expected = 90000000 * (0.01 + 0.005)
        self.assertAlmostEqual(actual, expected, places=8)

    def test_get_coin_now_money_returns_zero_when_ticker_is_missing(self):
        """잔고에 없는 코인을 조회하면 총 매수 금액 0을 반환하는지 확인합니다."""

        actual = lib.get_coin_now_money(self.sample_balances, "KRW-XRP")
        self.assertEqual(actual, 0.0)

    def test_get_has_coin_count_excludes_krw_and_zero_avg_buy_price(self):
        """원화와 평균매입단가 0인 코인을 제외하고 보유 코인 수를 세는지 확인합니다."""

        actual = lib.get_has_coin_count(self.sample_balances)
        self.assertEqual(actual, 2)

    def test_get_avg_buy_price(self):
        """특정 코인의 평균 매입 단가를 정확히 반환하는지 확인합니다."""

        actual = lib.get_avg_buy_price(self.sample_balances, "KRW-ETH")
        self.assertEqual(actual, 4000000.0)

    def test_get_avg_buy_price_returns_zero_when_ticker_is_missing(self):
        """잔고에 없는 코인의 평균 매입 단가는 0을 반환하는지 확인합니다."""

        actual = lib.get_avg_buy_price(self.sample_balances, "KRW-XRP")
        self.assertEqual(actual, 0.0)

    def test_get_total_money(self):
        """원화와 각 코인 매수 원가를 합산한 총 원금이 정확한지 확인합니다."""

        actual = lib.get_total_money(self.sample_balances)
        expected = (
            500000
            + 10000
            + 90000000 * (0.01 + 0.005)
            + 4000000 * 0.2
        )
        self.assertAlmostEqual(actual, expected, places=8)

    def test_get_total_money_ignores_invalid_balance_rows(self):
        """형식이 잘못된 잔고 행이 있어도 건너뛰고 나머지 금액만 합산하는지 확인합니다."""

        broken_balances = self.sample_balances + [
            {
                "currency": "XRP",
                "balance": "not-a-number",
                "locked": "0",
                "avg_buy_price": "1000",
                "unit_currency": "KRW",
            }
        ]

        actual = lib.get_total_money(broken_balances)
        expected = (
            500000
            + 10000
            + 90000000 * (0.01 + 0.005)
            + 4000000 * 0.2
        )
        self.assertAlmostEqual(actual, expected, places=8)

    def test_get_ticker_prices_batches_requests(self):
        """여러 티커 조회 시 배치 단위로 현재가를 묶어서 요청하는지 확인합니다."""

        tickers = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]

        with patch.object(lib.pyupbit, "get_current_price") as mock_get_current_price:
            mock_get_current_price.side_effect = [
                {"KRW-BTC": 100.0, "KRW-ETH": 200.0},
                {"KRW-XRP": 300.0},
            ]

            prices = lib.get_ticker_prices(tickers, batch_size=2)

        self.assertEqual(
            mock_get_current_price.call_args_list[0].args[0],
            ["KRW-BTC", "KRW-ETH"],
        )
        self.assertEqual(mock_get_current_price.call_args_list[1].args[0], ["KRW-XRP"])
        self.assertEqual(
            prices,
            {"KRW-BTC": 100.0, "KRW-ETH": 200.0, "KRW-XRP": 300.0},
        )

    def test_get_top_coin_list_uses_cache(self):
        """짧은 시간 안의 같은 요청은 캐시를 재사용해 중복 조회를 줄이는지 확인합니다."""

        lib._TOP_COIN_LIST_CACHE.clear()

        with patch.object(lib, "list_krw_tickers", return_value=["KRW-BTC", "KRW-ETH"]):
            with patch.object(lib, "get_ohlcv") as mock_get_ohlcv:
                mock_get_ohlcv.side_effect = [
                    pd.DataFrame(
                        {"close": [100, 110], "volume": [10, 20]}
                    ),
                    pd.DataFrame(
                        {"close": [50, 60], "volume": [5, 6]}
                    ),
                ]

                first = lib.get_top_coin_list("day", 2, cache_seconds=60)
                second = lib.get_top_coin_list("day", 2, cache_seconds=60)

        self.assertEqual(first, second)
        self.assertEqual(mock_get_ohlcv.call_count, 2)


if __name__ == "__main__":
    unittest.main()
