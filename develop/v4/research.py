"""V4 후보 전략을 같은 과거 구간에서 빠르게 선별하는 연구 도구입니다."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import isnan
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.v3.backtesting.backtest_logic import (  # noqa: E402
    build_strategy_ohlcv,
    select_source_interval,
)
from develop.v3.backtesting.ohlcv_cache import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    get_cached_strategy_anchor,
    load_cached_ohlcv,
)
from develop.v4.config import V4_CONFIG  # noqa: E402
from develop.v4.trade_logic import build_signal  # noqa: E402


@dataclass(frozen=True)
class CandidateConfig:
    """V4 연구에서 비교할 RSI 회복 진입·청산 후보의 설정입니다."""

    entry_mode: str  # ``oversold``는 과매도 중 진입, ``recovery``는 과매도 탈출 때 진입합니다.
    buy_threshold: float  # 매수에 사용할 RSI 과매도 기준값입니다.
    sell_threshold: float  # RSI 청산에 사용할 과매수 기준값입니다.
    take_profit_pct: float  # RSI와 무관하게 전량 익절할 수익률(%)입니다. 0이면 사용하지 않습니다.
    stop_loss_pct: float  # RSI와 무관하게 전량 손절할 손실률(%)입니다. 0이면 사용하지 않습니다.
    buy_ratio: float  # 매수 때 가용 원화 중 사용할 비율입니다.


@dataclass(frozen=True)
class CandidateResult:
    """후보 하나의 수익률·낙폭·체결 횟수를 담는 연구 결과입니다."""

    config: CandidateConfig  # 평가한 후보 전략 설정입니다.
    total_return_pct: float  # 시작 원금 대비 최종 수익률(%)입니다.
    max_drawdown_pct: float  # 고점 대비 최대 자산 하락률(%)입니다.
    trades: int  # 가상 매수·매도 체결 총횟수입니다.


def build_research_snapshots(
    source_ohlcv: pd.DataFrame,
    strategy_candle_anchor: pd.Timestamp,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
    cron_interval_minutes: int,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, list[pd.Timestamp]]:
    """V3와 같은 부분 4시간 봉 RSI와 다음 원본 봉 시가를 연구용으로 한 번 계산합니다.

    RSI를 후보마다 다시 계산하지 않아도 되도록 V4 백테스트와 같은 방식으로 현재·이전
    RSI 스냅샷을 먼저 만듭니다. 이전 RSI는 직전 1시간 RSI가 아니라 직전 4시간 전략 봉의
    RSI이므로, V4의 회복 진입 판단과 정확히 같은 값입니다.

    Args:
        source_ohlcv: 크론 간격에 맞는 시간순 원본 OHLCV 데이터입니다.
        strategy_candle_anchor: 업비트 4시간 봉의 실제 시작 시각입니다.
        start_time: 연구 성과를 계산할 포함 시작 시각입니다.
        end_time: 연구 성과를 계산할 배타적 종료 시각입니다.
        cron_interval_minutes: V4 연구에서 가정할 봇 실행 간격(분)입니다.

    Returns:
        시간순 ``(현재_RSI, 이전_RSI, 신호_종가, 다음_원본봉_시가, 크론_판단_시각)`` 튜플입니다.
    """

    source_duration = pd.Timedelta(source_ohlcv.index.to_series().diff().dropna().min())
    event_times = source_ohlcv.index + source_duration
    rsi = pd.Series(index=event_times, dtype=float, name="RSI")
    previous_rsi = pd.Series(index=event_times, dtype=float, name="previous_RSI")
    evaluation_times: list[pd.Timestamp] = []
    cron_duration = pd.Timedelta(minutes=cron_interval_minutes)

    for position, (source_candle_start, _) in enumerate(source_ohlcv.iterrows()):
        signal_time = source_candle_start + source_duration
        strategy_ohlcv = build_strategy_ohlcv(
            source_ohlcv.iloc[: position + 1],
            V4_CONFIG.interval,
            strategy_candle_anchor,
        )
        if len(strategy_ohlcv) < V4_CONFIG.strategy.rsi_period + 2:
            continue

        signal = build_signal(strategy_ohlcv, V4_CONFIG.strategy)
        rsi.iloc[position] = signal.rsi
        previous_rsi.iloc[position] = signal.previous_rsi
        if position >= len(source_ohlcv) - 1 or signal_time < start_time or signal_time >= end_time:
            continue
        if (signal_time - signal_time.normalize()) % cron_duration == pd.Timedelta(0):
            evaluation_times.append(signal_time)

    visible_mask = (event_times >= start_time) & (event_times < end_time)
    rsi = rsi.loc[visible_mask]
    previous_rsi = previous_rsi.loc[visible_mask]
    close_prices = pd.Series(source_ohlcv["close"].to_numpy(), index=event_times, name="close").loc[visible_mask]
    execution_opens = pd.Series(
        source_ohlcv["open"].shift(-1).to_numpy(),
        index=source_ohlcv.index + source_duration,
        name="execution_open",
    )
    return rsi, previous_rsi, close_prices, execution_opens.reindex(rsi.index), evaluation_times


def simulate_candidate(
    rsi: pd.Series,
    previous_rsi: pd.Series,
    close_prices: pd.Series,
    execution_opens: pd.Series,
    evaluation_times: list[pd.Timestamp],
    candidate: CandidateConfig,
    initial_capital: float = 1_000_000.0,
    fee_rate: float = 0.0005,
    min_trade_krw: float = 5_000.0,
) -> CandidateResult:
    """후보를 신호 뒤 다음 4시간 봉 시가 체결 가정으로 빠르게 시뮬레이션합니다.

    Args:
        rsi: V3와 같은 방식으로 계산한 시간순 RSI 시리즈입니다.
        previous_rsi: 직전 전략 봉에서 계산한 시간순 RSI 시리즈입니다.
        close_prices: 각 RSI 신호 시점의 원본 봉 종가 시리즈입니다.
        execution_opens: 신호 이후 다음 원본 봉의 가상 체결 시가 시리즈입니다.
        evaluation_times: 크론 가정에 따라 실제 주문을 판단할 시각 목록입니다.
        candidate: 비교할 RSI 진입·청산·손익 관리 후보 설정입니다.
        initial_capital: 시뮬레이션 시작 원화입니다.
        fee_rate: 매수·매도 때 각각 적용할 수수료 비율입니다.
        min_trade_krw: 주문으로 인정할 최소 원화 금액입니다.

    Returns:
        후보의 총수익률, 최대 낙폭, 실제 체결 횟수입니다.
    """

    rsi_values = rsi.to_numpy(dtype=float)
    previous_rsi_values = previous_rsi.reindex(rsi.index).to_numpy(dtype=float)
    close_values = close_prices.reindex(rsi.index).to_numpy(dtype=float)
    open_values = execution_opens.reindex(rsi.index).to_numpy(dtype=float)
    evaluation_positions = rsi.index.get_indexer(pd.DatetimeIndex(evaluation_times))
    cash = initial_capital
    coin_amount = 0.0
    average_buy_price = 0.0
    peak_equity = initial_capital
    max_drawdown_pct = 0.0
    trades = 0

    for position in evaluation_positions:
        if position < 1:
            continue
        current_rsi = rsi_values[position]
        previous_rsi_value = previous_rsi_values[position]
        execution_price = open_values[position]
        if isnan(current_rsi) or isnan(previous_rsi_value) or isnan(execution_price):
            continue

        current_close = close_values[position]
        if isnan(current_close) or execution_price <= 0:
            continue

        if coin_amount > 0:
            profit_rate = (current_close - average_buy_price) / average_buy_price * 100
            should_stop = candidate.stop_loss_pct > 0 and profit_rate <= -candidate.stop_loss_pct
            should_take_profit = candidate.take_profit_pct > 0 and profit_rate >= candidate.take_profit_pct
            should_sell_by_rsi = current_rsi >= candidate.sell_threshold
            if should_stop or should_take_profit or should_sell_by_rsi:
                cash += coin_amount * execution_price * (1 - fee_rate)
                coin_amount = 0.0
                average_buy_price = 0.0
                trades += 1
        else:
            is_oversold = current_rsi <= candidate.buy_threshold
            has_recovered = previous_rsi_value < candidate.buy_threshold <= current_rsi
            should_buy = is_oversold if candidate.entry_mode == "oversold" else has_recovered
            order_amount = cash * candidate.buy_ratio
            if should_buy and order_amount >= min_trade_krw:
                coin_amount = order_amount * (1 - fee_rate) / execution_price
                cash -= order_amount
                # V4 백테스트와 동일하게 매수 수수료까지 평균 매수가에 반영합니다.
                average_buy_price = order_amount / coin_amount
                trades += 1

        equity = cash + coin_amount * current_close
        peak_equity = max(peak_equity, equity)
        max_drawdown_pct = min(max_drawdown_pct, (equity / peak_equity - 1) * 100)

    final_equity = cash + coin_amount * close_values[-1]
    return CandidateResult(
        config=candidate,
        total_return_pct=(final_equity / initial_capital - 1) * 100,
        max_drawdown_pct=max_drawdown_pct,
        trades=trades,
    )


def find_candidates(
    rsi: pd.Series,
    previous_rsi: pd.Series,
    close_prices: pd.Series,
    execution_opens: pd.Series,
    evaluation_times: list[pd.Timestamp],
) -> list[CandidateResult]:
    """작은 파라미터 격자에서 과도한 체결을 제외한 후보를 수익률 순으로 반환합니다.

    Args:
        rsi: V3와 같은 부분 전략 봉으로 계산한 시간순 RSI 시리즈입니다.
        previous_rsi: 직전 전략 봉으로 계산한 시간순 RSI 시리즈입니다.
        close_prices: 신호 시점 원본 봉 종가 시리즈입니다.
        execution_opens: 신호 뒤 다음 원본 봉 시가 시리즈입니다.
        evaluation_times: 크론 가정에 따라 실제 주문을 판단할 시각 목록입니다.

    Returns:
        최소 4회, 최대 80회 체결한 후보를 수익률 내림차순·낙폭 오름차순으로 정렬한 목록입니다.
    """

    results: list[CandidateResult] = []
    for entry_mode in ("oversold", "recovery"):
        for buy_threshold in (20.0, 25.0, 30.0, 35.0, 40.0):
            for sell_threshold in (55.0, 60.0, 65.0, 70.0, 75.0):
                for take_profit_pct in (0.0, 3.0, 5.0, 8.0, 12.0):
                    for stop_loss_pct in (0.0, 5.0, 10.0, 15.0):
                        for buy_ratio in (0.2, 0.5, 1.0):
                            candidate = CandidateConfig(
                                entry_mode,
                                buy_threshold,
                                sell_threshold,
                                take_profit_pct,
                                stop_loss_pct,
                                buy_ratio,
                            )
                            result = simulate_candidate(
                                rsi,
                                previous_rsi,
                                close_prices,
                                execution_opens,
                                evaluation_times,
                                candidate,
                            )
                            if 4 <= result.trades <= 80:
                                results.append(result)
    return sorted(results, key=lambda result: (-result.total_return_pct, -result.max_drawdown_pct))


def parse_args() -> argparse.Namespace:
    """연구 대상 기간과 출력할 후보 개수를 CLI에서 읽습니다."""

    parser = argparse.ArgumentParser(description="Screen V4 RSI candidate strategies on cached OHLCV data.")
    parser.add_argument("--from", dest="start_date", default="2026-01-01", help="성과 계산 시작일(YYYY-MM-DD)")
    parser.add_argument("--to", dest="end_date", default="2026-08-03", help="성과 계산 종료일(YYYY-MM-DD, 포함)")
    parser.add_argument("--cron-interval-minutes", type=int, default=60, help="가정할 crontab 실행 간격(분)")
    parser.add_argument("--top", type=int, default=10, help="출력할 상위 후보 개수")
    return parser.parse_args()


def main() -> None:
    """캐시된 ETH 30분봉으로 V4 후보 연구 결과를 출력합니다."""

    args = parse_args()
    start_time = pd.Timestamp(args.start_date)
    end_time = pd.Timestamp(args.end_date) + pd.Timedelta(days=1)
    source_interval = select_source_interval(args.cron_interval_minutes)
    source_ohlcv = load_cached_ohlcv(DEFAULT_CACHE_DIR, "KRW-ETH", source_interval)
    anchor = get_cached_strategy_anchor(DEFAULT_CACHE_DIR, "KRW-ETH", source_interval, "minute240")
    if source_ohlcv.empty or anchor is None:
        raise SystemExit(f"V3 {source_interval} cache and minute240 anchor are required. Run the V3 backtest first.")

    rsi, previous_rsi, close_prices, execution_opens, evaluation_times = build_research_snapshots(
        source_ohlcv,
        anchor,
        start_time,
        end_time,
        args.cron_interval_minutes,
    )
    candidates = find_candidates(rsi, previous_rsi, close_prices, execution_opens, evaluation_times)
    for rank, result in enumerate(candidates[: args.top], start=1):
        config = result.config
        print(
            f"{rank}. return={result.total_return_pct:.2f}% drawdown={result.max_drawdown_pct:.2f}% "
            f"trades={result.trades} entry={config.entry_mode} buy={config.buy_threshold:g} "
            f"sell={config.sell_threshold:g} take_profit={config.take_profit_pct:g}% "
            f"stop_loss={config.stop_loss_pct:g}% buy_ratio={config.buy_ratio:g}"
        )


if __name__ == "__main__":
    main()
