import tempfile
import unittest
from pathlib import Path

import pandas as pd

from develop.v3.backtesting.ohlcv_cache import (
    OhlcvRange,
    get_cached_strategy_anchor,
    get_or_fetch_cached_ohlcv,
    save_strategy_anchor,
)


class OhlcvCacheTest(unittest.TestCase):
    """V3 백테스트 OHLCV CSV 캐시의 누락 구간 조회·재사용을 검증합니다."""

    def setUp(self) -> None:
        """각 테스트가 독립적으로 사용할 임시 캐시 폴더와 30분 봉 길이를 준비합니다."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temporary_directory.name)
        self.source_duration = pd.Timedelta(minutes=30)
        self.fetch_calls: list[tuple[int, pd.Timestamp]] = []

    def tearDown(self) -> None:
        """테스트가 만든 임시 캐시 폴더를 삭제합니다."""

        self.temporary_directory.cleanup()

    def fake_fetcher(
        self,
        ticker: str,
        interval: str,
        count: int,
        to: pd.Timestamp,
    ) -> pd.DataFrame:
        """요청한 ``to + count`` 범위의 합성 30분 OHLCV 데이터를 반환합니다.

        Args:
            ticker: 실제 API와 같은 호출 형태를 검증하기 위한 마켓 티커입니다.
            interval: 실제 API와 같은 호출 형태를 검증하기 위한 원본 봉 간격입니다.
            count: ``to`` 이전에 만들어 반환할 합성 원본 봉 개수입니다.
            to: 반환 데이터의 배타적 종료 시각입니다.

        Returns:
            ``to`` 이전의 시간순 합성 ``open``·``close`` OHLCV 데이터입니다.
        """

        self.assertEqual(ticker, "KRW-ETH")
        self.assertEqual(interval, "minute30")
        self.fetch_calls.append((count, to))
        index = pd.date_range(to - self.source_duration * count, periods=count, freq=self.source_duration)
        values = list(range(len(index)))
        return pd.DataFrame({"open": values, "close": values}, index=index)

    def sparse_fetcher(
        self,
        ticker: str,
        interval: str,
        count: int,
        to: pd.Timestamp,
    ) -> pd.DataFrame:
        """일부 원본 봉을 생략하는 거래소 응답을 흉내 냅니다.

        실제 업비트는 체결이 없는 시간의 봉을 반환하지 않을 수 있으므로, CSV에 없는 봉을
        매 실행마다 다시 호출하지 않는지 검증하기 위해 사용합니다.
        """

        frame = self.fake_fetcher(ticker, interval, count, to)
        return frame.drop(pd.Timestamp("2026-07-01 01:00:00"), errors="ignore")

    # 4월~6월 캐시가 있을 때 1월~8월 요청은 캐시 양쪽의 빈 구간만 API로 채운다.
    def test_expanded_range_fetches_only_missing_left_and_right_ranges(self) -> None:
        """기존 캐시 가운데 구간을 재사용하고 앞·뒤 두 API 요청만 만드는지 확인합니다."""

        cached_range = OhlcvRange(
            pd.Timestamp("2026-04-15 00:00:00"),
            pd.Timestamp("2026-06-16 00:00:00"),
        )
        get_or_fetch_cached_ohlcv(
            "KRW-ETH",
            "minute30",
            cached_range,
            self.source_duration,
            self.fake_fetcher,
            self.cache_dir,
        )

        self.fetch_calls.clear()
        expanded = get_or_fetch_cached_ohlcv(
            "KRW-ETH",
            "minute30",
            OhlcvRange(
                pd.Timestamp("2026-01-01 00:00:00"),
                pd.Timestamp("2026-08-02 00:00:00"),
            ),
            self.source_duration,
            self.fake_fetcher,
            self.cache_dir,
        )

        self.assertEqual(len(self.fetch_calls), 2)
        self.assertEqual(
            {call[1] for call in self.fetch_calls},
            {pd.Timestamp("2026-04-15 00:00:00"), pd.Timestamp("2026-08-02 00:00:00")},
        )
        self.assertEqual(expanded.index[0], pd.Timestamp("2026-01-01 00:00:00"))
        self.assertEqual(expanded.index[-1], pd.Timestamp("2026-08-01 23:30:00"))

        self.fetch_calls.clear()
        get_or_fetch_cached_ohlcv(
            "KRW-ETH",
            "minute30",
            OhlcvRange(
                pd.Timestamp("2026-01-01 00:00:00"),
                pd.Timestamp("2026-08-02 00:00:00"),
            ),
            self.source_duration,
            self.fake_fetcher,
            self.cache_dir,
        )
        self.assertEqual(self.fetch_calls, [])

    # 거래소가 원본 봉 하나를 생략해도 완료 조회 범위를 기록하여 다음 실행은 API를 재호출하지 않는다.
    def test_known_exchange_candle_gap_is_not_refetched(self) -> None:
        """체결 없는 시각이 CSV에 없어도 해당 시간 범위를 캐시 완료로 재사용하는지 확인합니다."""

        requested_range = OhlcvRange(
            pd.Timestamp("2026-07-01 00:00:00"),
            pd.Timestamp("2026-07-01 03:00:00"),
        )
        first_result = get_or_fetch_cached_ohlcv(
            "KRW-ETH",
            "minute30",
            requested_range,
            self.source_duration,
            self.sparse_fetcher,
            self.cache_dir,
        )

        self.assertNotIn(pd.Timestamp("2026-07-01 01:00:00"), first_result.index)
        self.assertEqual(len(self.fetch_calls), 1)

        self.fetch_calls.clear()
        second_result = get_or_fetch_cached_ohlcv(
            "KRW-ETH",
            "minute30",
            requested_range,
            self.source_duration,
            self.sparse_fetcher,
            self.cache_dir,
        )

        self.assertEqual(self.fetch_calls, [])
        self.assertNotIn(pd.Timestamp("2026-07-01 01:00:00"), second_result.index)

    # 전략 봉 시작 시각을 메타데이터에 저장하면 다음 실행에서 API 없이 같은 경계를 사용한다.
    def test_strategy_anchor_is_reused_from_cache_metadata(self) -> None:
        """전략 봉 시작 시각이 티커·원본 봉·전략 봉별로 저장·복원되는지 확인합니다."""

        anchor = pd.Timestamp("2026-08-02 17:00:00")
        save_strategy_anchor(
            self.cache_dir,
            "KRW-ETH",
            "minute30",
            "minute240",
            anchor,
        )

        restored_anchor = get_cached_strategy_anchor(
            self.cache_dir,
            "KRW-ETH",
            "minute30",
            "minute240",
        )

        self.assertEqual(restored_anchor, anchor)
