"""V3 백테스트용 완료 OHLCV 캔들을 CSV로 재사용하는 로컬 캐시입니다."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from math import ceil
from pathlib import Path

import pandas as pd

CacheFetcher = Callable[[str, str, int, pd.Timestamp], pd.DataFrame]
DEFAULT_CACHE_DIR = Path(__file__).with_name("cache")


@dataclass(frozen=True)
class OhlcvRange:
    """원본 OHLCV 봉 시작 시각 기준의 포함·배타적 시간 범위입니다."""

    start: pd.Timestamp  # 캐시 또는 API에서 확보해야 하는 첫 원본 봉의 시작 시각입니다.
    end: pd.Timestamp  # 확보 범위의 배타적 종료 시각입니다.


def cache_file_path(cache_dir: Path, ticker: str, interval: str) -> Path:
    """티커와 원본 봉 간격에 대응하는 CSV 캐시 파일 경로를 반환합니다.

    Args:
        cache_dir: V3 백테스트 OHLCV 캐시를 저장할 디렉터리입니다.
        ticker: ``KRW-ETH``처럼 캐시를 분리할 업비트 마켓 티커입니다.
        interval: ``minute30``처럼 캐시를 분리할 원본 봉 간격입니다.

    Returns:
        티커·간격별 CSV 파일 경로입니다.
    """

    safe_ticker = ticker.replace("/", "_")
    return cache_dir / f"{safe_ticker}__{interval}.csv"


def cache_metadata_path(cache_dir: Path, ticker: str, interval: str) -> Path:
    """조회 완료 범위와 전략 봉 시작 시각을 저장할 메타데이터 경로를 반환합니다.

    Args:
        cache_dir: V3 백테스트 OHLCV 캐시를 저장할 디렉터리입니다.
        ticker: ``KRW-ETH``처럼 메타데이터를 분리할 업비트 마켓 티커입니다.
        interval: 메타데이터가 연결된 원본 봉 간격입니다.

    Returns:
        조회 완료 범위와 전략 봉 시작 시각 메타데이터 JSON 파일 경로입니다.
    """

    return cache_file_path(cache_dir, ticker, interval).with_suffix(".json")


def _read_metadata(cache_dir: Path, ticker: str, interval: str) -> dict[str, object]:
    """캐시 메타데이터를 읽고, 파일이 없으면 기본 구조를 반환합니다."""

    path = cache_metadata_path(cache_dir, ticker, interval)
    if not path.exists():
        return {"coverage_ranges": [], "strategy_anchors": {}}

    metadata = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"Invalid OHLCV cache metadata: {path}")
    metadata.setdefault("coverage_ranges", [])
    metadata.setdefault("strategy_anchors", {})
    return metadata


def _write_metadata(cache_dir: Path, ticker: str, interval: str, metadata: dict[str, object]) -> None:
    """캐시 메타데이터를 임시 파일을 거쳐 안전하게 저장합니다."""

    path = cache_metadata_path(cache_dir, ticker, interval)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(path)


def load_cached_ohlcv(cache_dir: Path, ticker: str, interval: str) -> pd.DataFrame:
    """로컬 CSV 캐시를 읽어 시간순 OHLCV 데이터로 반환합니다.

    Args:
        cache_dir: V3 백테스트 OHLCV 캐시를 저장한 디렉터리입니다.
        ticker: 읽을 캐시의 업비트 마켓 티커입니다.
        interval: 읽을 캐시의 원본 봉 간격입니다.

    Returns:
        캐시가 없으면 빈 데이터프레임, 있으면 중복을 제거한 시간순 OHLCV 데이터입니다.

    Raises:
        ValueError: CSV에 ``timestamp`` 컬럼이 없거나 같은 시각의 봉이 중복될 때 발생합니다.
    """

    path = cache_file_path(cache_dir, ticker, interval)
    if not path.exists():
        return pd.DataFrame()

    cached = pd.read_csv(path, index_col="timestamp", parse_dates=["timestamp"])
    if not isinstance(cached.index, pd.DatetimeIndex):
        raise ValueError(f"Invalid OHLCV cache index: {path}")
    if not cached.index.is_unique:
        raise ValueError(f"Duplicate OHLCV timestamps in cache: {path}")
    return cached.sort_index()


def merge_ohlcv(*frames: pd.DataFrame) -> pd.DataFrame:
    """기존 캐시와 새 API 응답을 합쳐 최신 응답을 우선한 시간순 데이터로 만듭니다.

    Args:
        frames: 시간 인덱스를 가진 OHLCV 데이터프레임들입니다. 뒤에 전달한 데이터가
            같은 시각의 기존 봉을 덮어씁니다.

    Returns:
        중복 시각을 제거하고 시간순으로 정렬한 OHLCV 데이터입니다.
    """

    non_empty_frames = [frame for frame in frames if not frame.empty]
    if not non_empty_frames:
        return pd.DataFrame()

    merged = pd.concat(non_empty_frames).sort_index()
    return merged.loc[~merged.index.duplicated(keep="last")]


def _merge_ranges(ranges: list[OhlcvRange]) -> list[OhlcvRange]:
    """겹치거나 맞닿은 시간 범위를 하나의 범위로 합칩니다."""

    if not ranges:
        return []

    merged_ranges: list[OhlcvRange] = []
    for current_range in sorted(ranges, key=lambda value: value.start):
        if current_range.end <= current_range.start:
            raise ValueError("OHLCV range end must be later than its start.")
        if not merged_ranges or merged_ranges[-1].end < current_range.start:
            merged_ranges.append(current_range)
            continue
        previous = merged_ranges[-1]
        merged_ranges[-1] = OhlcvRange(previous.start, max(previous.end, current_range.end))
    return merged_ranges


def _infer_coverage_ranges(cached_ohlcv: pd.DataFrame, source_duration: pd.Timedelta) -> list[OhlcvRange]:
    """기존 CSV만 있는 캐시를 위해 연속된 봉 구간을 완료 조회 범위로 추정합니다."""

    if cached_ohlcv.empty:
        return []

    timestamps = cached_ohlcv.index.sort_values()
    ranges: list[OhlcvRange] = []
    range_start = timestamps[0]
    previous = range_start
    for timestamp in timestamps[1:]:
        if timestamp - previous != source_duration:
            ranges.append(OhlcvRange(range_start, previous + source_duration))
            range_start = timestamp
        previous = timestamp
    ranges.append(OhlcvRange(range_start, previous + source_duration))
    return ranges


def load_coverage_ranges(
    cache_dir: Path,
    ticker: str,
    interval: str,
    cached_ohlcv: pd.DataFrame,
    source_duration: pd.Timedelta,
) -> list[OhlcvRange]:
    """API 조회가 완료된 시간 범위를 읽고, 구형 CSV 캐시는 연속 봉 기준으로 복원합니다.

    업비트는 해당 구간에 체결이 없으면 캔들을 생략할 수 있습니다. 따라서 CSV에 특정 봉이
    없다는 사실만으로 API를 다시 호출하지 않도록, 성공적으로 조회한 시간 범위를 별도로
    저장합니다. 메타데이터가 없는 기존 CSV는 한 번만 공백을 확인할 수 있도록 연속된 봉
    묶음으로 보수적으로 복원합니다.

    Args:
        cache_dir: CSV 캐시와 메타데이터가 저장된 디렉터리입니다.
        ticker: 조회 범위를 읽을 업비트 마켓 티커입니다.
        interval: 조회 범위를 읽을 원본 봉 간격입니다.
        cached_ohlcv: 이미 읽어 둔 원본 OHLCV CSV 데이터입니다.
        source_duration: 한 원본 봉의 시간 길이입니다.

    Returns:
        API 조회가 완료된 겹치지 않는 시간 범위 목록입니다.
    """

    if cached_ohlcv.empty:
        return []

    metadata = _read_metadata(cache_dir, ticker, interval)
    raw_ranges = metadata.get("coverage_ranges", [])
    if raw_ranges:
        try:
            ranges = [
                OhlcvRange(pd.Timestamp(value["start"]), pd.Timestamp(value["end"]))
                for value in raw_ranges
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid OHLCV cache coverage metadata.") from error
        return _merge_ranges(ranges)
    return _infer_coverage_ranges(cached_ohlcv, source_duration)


def find_uncovered_ranges(
    covered_ranges: list[OhlcvRange],
    requested_range: OhlcvRange,
) -> list[OhlcvRange]:
    """요청 범위 중 API로 아직 확인하지 않은 연속 시간 범위만 반환합니다.

    Args:
        covered_ranges: 이전 API 호출이 완료된 원본 봉 시간 범위들입니다.
        requested_range: 이번 백테스트에 필요한 원본 봉 시간 범위입니다.

    Returns:
        새 API 호출이 필요한 겹치지 않는 시간 범위 목록입니다.
    """

    if requested_range.end <= requested_range.start:
        raise ValueError("requested_range.end must be later than requested_range.start.")

    missing_ranges: list[OhlcvRange] = []
    cursor = requested_range.start
    for covered_range in _merge_ranges(covered_ranges):
        if covered_range.end <= cursor:
            continue
        if covered_range.start >= requested_range.end:
            break
        if covered_range.start > cursor:
            missing_ranges.append(OhlcvRange(cursor, min(covered_range.start, requested_range.end)))
        cursor = max(cursor, covered_range.end)
        if cursor >= requested_range.end:
            break
    if cursor < requested_range.end:
        missing_ranges.append(OhlcvRange(cursor, requested_range.end))
    return missing_ranges


def save_coverage_ranges(
    cache_dir: Path,
    ticker: str,
    interval: str,
    covered_ranges: list[OhlcvRange],
) -> None:
    """성공적으로 조회한 시간 범위를 캐시 메타데이터에 저장합니다."""

    metadata = _read_metadata(cache_dir, ticker, interval)
    metadata["coverage_ranges"] = [
        {"start": str(covered_range.start), "end": str(covered_range.end)}
        for covered_range in _merge_ranges(covered_ranges)
    ]
    _write_metadata(cache_dir, ticker, interval, metadata)


def _fetch_range(
    fetcher: CacheFetcher,
    ticker: str,
    interval: str,
    missing_range: OhlcvRange,
    source_duration: pd.Timedelta,
) -> pd.DataFrame:
    """pyupbit의 ``to + count`` 방식으로 하나의 빈 원본 봉 구간을 조회합니다."""

    required_count = ceil((missing_range.end - missing_range.start) / source_duration) + 2
    fetched = fetcher(ticker, interval, required_count, missing_range.end)
    return fetched.loc[(fetched.index >= missing_range.start) & (fetched.index < missing_range.end)]


def save_cached_ohlcv(
    cache_dir: Path,
    ticker: str,
    interval: str,
    ohlcv: pd.DataFrame,
) -> None:
    """완료된 원본 OHLCV를 임시 파일을 거쳐 CSV 캐시에 안전하게 저장합니다.

    Args:
        cache_dir: CSV 캐시를 저장할 디렉터리입니다. 없으면 자동으로 만듭니다.
        ticker: 저장할 캐시의 업비트 마켓 티커입니다.
        interval: 저장할 캐시의 원본 봉 간격입니다.
        ohlcv: 중복이 제거된 시간순 완료 OHLCV 데이터입니다.
    """

    path = cache_file_path(cache_dir, ticker, interval)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    ohlcv.sort_index().to_csv(temporary_path, index_label="timestamp")
    temporary_path.replace(path)


def get_cached_strategy_anchor(
    cache_dir: Path,
    ticker: str,
    source_interval: str,
    strategy_interval: str,
) -> pd.Timestamp | None:
    """캐시에 저장된 업비트 전략 봉 시작 시각을 반환합니다.

    Args:
        cache_dir: OHLCV 캐시·메타데이터가 저장된 디렉터리입니다.
        ticker: 전략 봉 시작 시각을 읽을 업비트 마켓 티커입니다.
        source_interval: 메타데이터가 연결된 원본 봉 간격입니다.
        strategy_interval: 시작 시각을 찾을 RSI 전략 봉 간격입니다.

    Returns:
        저장된 시작 시각 또는 해당 전략 봉 메타데이터가 없을 때 ``None``입니다.
    """

    path = cache_metadata_path(cache_dir, ticker, source_interval)
    if not path.exists():
        return None

    metadata = _read_metadata(cache_dir, ticker, source_interval)
    value = metadata.get("strategy_anchors", {}).get(strategy_interval)
    return pd.Timestamp(value) if value is not None else None


def save_strategy_anchor(
    cache_dir: Path,
    ticker: str,
    source_interval: str,
    strategy_interval: str,
    strategy_anchor: pd.Timestamp,
) -> None:
    """업비트 전략 봉 시작 시각을 캐시 메타데이터에 저장합니다.

    Args:
        cache_dir: OHLCV 캐시·메타데이터를 저장할 디렉터리입니다.
        ticker: 전략 봉 시작 시각을 저장할 업비트 마켓 티커입니다.
        source_interval: 메타데이터가 연결된 원본 봉 간격입니다.
        strategy_interval: 시작 시각을 저장할 RSI 전략 봉 간격입니다.
        strategy_anchor: 업비트가 반환한 전략 봉의 실제 시작 시각입니다.
    """

    metadata = _read_metadata(cache_dir, ticker, source_interval)
    metadata.setdefault("strategy_anchors", {})[strategy_interval] = str(strategy_anchor)
    _write_metadata(cache_dir, ticker, source_interval, metadata)


def get_or_fetch_cached_ohlcv(
    ticker: str,
    interval: str,
    requested_range: OhlcvRange,
    source_duration: pd.Timedelta,
    fetcher: CacheFetcher,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> pd.DataFrame:
    """캐시의 빈 구간만 API로 보완한 뒤 요청 범위의 완료 OHLCV를 반환합니다.

    Args:
        ticker: 조회·캐시할 업비트 마켓 티커입니다.
        interval: 조회·캐시할 원본 봉 간격입니다.
        requested_range: RSI 준비 구간까지 포함한 원본 봉 시작 시각 범위입니다.
        source_duration: 한 원본 봉의 시간 길이입니다.
        fetcher: ``(ticker, interval, count, to)`` 형태로 업비트 OHLCV를 반환하는 함수입니다.
        cache_dir: 티커·간격별 CSV와 메타데이터를 저장할 로컬 디렉터리입니다.

    Returns:
        캐시와 새 API 응답을 합친 뒤 요청 범위로 자른 시간순 OHLCV 데이터입니다.

    Raises:
        ValueError: API 응답과 캐시를 합쳐도 요청 범위의 OHLCV가 없을 때 발생합니다.
    """

    cached = load_cached_ohlcv(cache_dir, ticker, interval)
    covered_ranges = load_coverage_ranges(
        cache_dir,
        ticker,
        interval,
        cached,
        source_duration,
    )
    missing_ranges = find_uncovered_ranges(covered_ranges, requested_range)
    fetched_frames = [
        _fetch_range(fetcher, ticker, interval, missing_range, source_duration)
        for missing_range in missing_ranges
    ]
    merged = merge_ohlcv(cached, *fetched_frames)
    requested_ohlcv = merged.loc[
        (merged.index >= requested_range.start) & (merged.index < requested_range.end)
    ]
    if requested_ohlcv.empty:
        raise ValueError(f"No cached OHLCV data is available for {ticker} ({interval}).")
    if not merged.empty and (missing_ranges or cached.empty):
        save_cached_ohlcv(cache_dir, ticker, interval, merged)
    if missing_ranges:
        # API 요청이 정상 완료됐다면, 체결이 없어 반환되지 않은 시간도 이미 확인한 구간입니다.
        # 이를 기록해야 실제 거래소 데이터 공백 때문에 매 실행마다 같은 API를 호출하지 않습니다.
        save_coverage_ranges(
            cache_dir,
            ticker,
            interval,
            [*covered_ranges, *missing_ranges],
        )
    return requested_ohlcv
