import unittest
from dataclasses import replace

import pandas as pd

from develop.v3.backtesting.backtest_logic import (
    build_strategy_ohlcv,
    run_backtest,
    validate_ohlcv,
)
from develop.v3.config import V3_CONFIG


class V3BacktestVisualizerTest(unittest.TestCase):
    """V3 순수 백테스트가 공용 설정과 체결 가정을 지키는지 검증합니다."""

    def make_ohlcv(self, closes: list[float]) -> pd.DataFrame:
        """종가 목록을 백테스트에 필요한 시가·종가 OHLCV 데이터로 변환합니다."""

        index = pd.date_range("2025-01-01", periods=len(closes), freq="4h")
        return pd.DataFrame(
            {
                "open": closes,
                "close": closes,
            },
            index=index,
        )

    def make_coarse_candle_config(self):
        """4시간 원본 캔들 테스트에 맞는 4시간 크론 가정 설정을 만듭니다."""

        return replace(
            V3_CONFIG,
            backtest=replace(V3_CONFIG.backtest, cron_interval_minutes=240),
        )

    def strategy_candle_anchor(self) -> pd.Timestamp:
        """합성 OHLCV가 자정부터 시작하는 테스트용 전략 봉 기준 시각을 반환합니다."""

        return pd.Timestamp("2025-01-01 00:00:00")

    # 백테스트에 필요한 시가 또는 종가가 없으면 명확한 오류를 낸다.
    def test_validate_ohlcv_requires_open_and_close_columns(self) -> None:
        """시가 또는 종가 컬럼이 없으면 백테스트를 거부하는지 확인합니다."""

        with self.assertRaisesRegex(ValueError, "open"):
            validate_ohlcv(pd.DataFrame({"close": [100.0] * 16}))

    # 원본 봉 종가로 낸 신호는 같은 시각의 다음 원본 봉 시가에 체결한다.
    def test_run_backtest_records_buy_at_next_candle_open(self) -> None:
        """원본 봉 종료 시각과 다음 원본 봉 시가 체결 시각이 같은지 확인합니다."""

        result = run_backtest(
            self.make_ohlcv([200.0 - index for index in range(20)]),
            self.make_coarse_candle_config(),
            self.strategy_candle_anchor(),
        )

        first_trade = result.trades[0]
        self.assertEqual(first_trade.action, "BUY")
        self.assertEqual(first_trade.execution_time, first_trade.signal_time)

    # 매수 뒤 상승 추세가 이어져 RSI와 목표 수익률을 모두 충족하면 익절 매도한다.
    def test_run_backtest_records_profit_sell(self) -> None:
        """매수 뒤 목표 수익률을 만족하면 익절 매도를 기록하는지 확인합니다."""

        closes = [200.0 - index for index in range(18)] + [183.0 + index * 5 for index in range(18)]
        result = run_backtest(
            self.make_ohlcv(closes),
            self.make_coarse_candle_config(),
            self.strategy_candle_anchor(),
        )

        actions = [trade.action for trade in result.trades]
        self.assertIn("BUY", actions)
        self.assertIn("SELL_PROFIT", actions)

    # 공용 설정의 매수 기준을 바꾸면 백테스트도 같은 기준을 사용한다.
    def test_run_backtest_uses_shared_trade_config(self) -> None:
        """공용 매수 기준을 바꾸면 백테스트 판단도 함께 바뀌는지 확인합니다."""

        no_buy_config = replace(
            V3_CONFIG,
            strategy=replace(
                V3_CONFIG.strategy,
                trade=replace(V3_CONFIG.strategy.trade, buy_threshold=-1.0),
            ),
            backtest=replace(V3_CONFIG.backtest, cron_interval_minutes=240),
        )

        result = run_backtest(
            self.make_ohlcv([200.0 - index for index in range(20)]),
            no_buy_config,
            self.strategy_candle_anchor(),
        )

        self.assertEqual(result.trades, [])

    # 3시간 크론 가정이면 1시간 원본 봉 중 자정 기준 3시간마다만 매매 판단한다.
    def test_run_backtest_uses_cron_interval_from_backtest_config(self) -> None:
        """크론 주기 설정이 백테스트의 신호 판단 시점을 제한하는지 확인합니다."""

        hourly_ohlcv = self.make_ohlcv([200.0 - index for index in range(40)])
        hourly_ohlcv.index = pd.date_range("2025-01-01", periods=len(hourly_ohlcv), freq="1h")
        cron_config = replace(
            V3_CONFIG,
            interval="minute60",
            backtest=replace(V3_CONFIG.backtest, cron_interval_minutes=180),
        )

        result = run_backtest(hourly_ohlcv, cron_config, self.strategy_candle_anchor())

        self.assertTrue(result.evaluation_times)
        self.assertTrue(all(timestamp.hour % 3 == 0 for timestamp in result.evaluation_times))

    # 업비트 4시간봉이 01시·05시처럼 자정 기준이 아닐 때도 같은 경계로 묶는다.
    def test_build_strategy_ohlcv_uses_exchange_candle_anchor(self) -> None:
        """거래소가 제공한 전략 봉 시작 시각을 기준으로 원본 봉을 묶는지 확인합니다."""

        source_ohlcv = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0],
                "close": [101.0, 102.0, 103.0, 104.0],
            },
            index=pd.to_datetime(
                [
                    "2025-01-01 12:30:00",
                    "2025-01-01 13:00:00",
                    "2025-01-01 13:30:00",
                    "2025-01-01 14:00:00",
                ]
            ),
        )

        strategy_ohlcv = build_strategy_ohlcv(
            source_ohlcv,
            "minute240",
            pd.Timestamp("2025-01-01 13:00:00"),
        )

        self.assertEqual(
            list(strategy_ohlcv.index),
            [pd.Timestamp("2025-01-01 09:00:00"), pd.Timestamp("2025-01-01 13:00:00")],
        )
        self.assertEqual(float(strategy_ohlcv.loc["2025-01-01 13:00:00", "open"]), 101.0)
