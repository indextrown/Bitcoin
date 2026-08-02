"""V4.1 추세 필터·쿨다운 후보를 같은 과거 OHLCV에서 비교하는 연구 도구입니다."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime
from math import isnan
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.v3.backtesting.backtest_logic import build_strategy_ohlcv, select_source_interval  # noqa: E402
from develop.v3.backtesting.ohlcv_cache import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    get_cached_strategy_anchor,
    load_cached_ohlcv,
)
from develop.upbit_develop_library import calculate_rsi_series  # noqa: E402
from develop.v4_1.config import V4_1_CONFIG  # noqa: E402
from develop.v4_1.trade_logic import (  # noqa: E402
    SignalSnapshot,
    TradeConfig,
    decide_trade,
)

TREND_SMA_PERIODS = (10, 20, 30, 50)  # 연구에서 추세 필터로 비교할 4시간 전략 봉 이동평균 기간입니다.


@dataclass(frozen=True)
class CandidateConfig:
    """V4.1 연구에서 비교할 추세·쿨다운·손익 관리 후보 설정입니다."""

    require_uptrend: bool  # 상승 추세 필터를 매수에 적용할지 여부입니다.
    trend_sma_period: int  # 상승 추세 필터가 사용할 4시간 전략 봉 이동평균 기간입니다.
    cooldown_hours: int  # 손절 뒤 재매수를 막을 시간입니다.
    buy_ratio: float  # 매수 신호마다 가용 원화에서 사용할 비율입니다.
    take_profit_pct: float  # RSI와 무관하게 전량 익절할 수익률(%)입니다.
    stop_loss_pct: float  # RSI와 무관하게 전량 손절할 손실률(%)입니다.


@dataclass(frozen=True)
class CandidateResult:
    """후보 하나의 수익률·최대 낙폭·체결 횟수를 담는 연구 결과입니다."""

    config: CandidateConfig  # 평가한 V4.1 후보 설정입니다.
    total_return_pct: float  # 시작 원금 대비 최종 수익률(%)입니다.
    max_drawdown_pct: float  # 모든 원본 봉 종가 기준 고점 대비 최대 자산 하락률(%)입니다.
    trades: int  # 백테스트에서 실제 체결한 매수·매도 주문의 총횟수입니다.


@dataclass(frozen=True)
class ResearchSnapshots:
    """V4.1 후보들이 공통으로 재사용하는 시간순 RSI·추세·체결 가격 입력입니다."""

    rsi: pd.Series  # 각 원본 봉 종료 시점의 현재 RSI입니다.
    previous_rsi: pd.Series  # 각 원본 봉 종료 시점의 직전 전략 봉 RSI입니다.
    close_prices: pd.Series  # 자산 평가와 신호 가격에 쓰는 원본 봉 종가입니다.
    execution_opens: pd.Series  # 신호 뒤 다음 원본 봉 시가입니다.
    trend_sma_by_period: dict[int, tuple[pd.Series, pd.Series]]  # 기간별 현재·이전 전략 봉 이동평균입니다.
    evaluation_times: set[pd.Timestamp]  # 크론 가정에 따라 주문을 판단할 시각입니다.
    source_duration: pd.Timedelta  # 원본 봉 하나가 나타내는 시간입니다.


def build_research_snapshots(
    source_ohlcv: pd.DataFrame,
    strategy_candle_anchor: pd.Timestamp,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
    cron_interval_minutes: int,
) -> ResearchSnapshots:
    """V4.1과 같은 부분 전략 봉 RSI·추세·다음 봉 시가를 한 번만 계산합니다.

    Args:
        source_ohlcv: 크론 간격에 맞는 시간순 원본 OHLCV 데이터입니다.
        strategy_candle_anchor: 업비트 4시간 봉의 실제 시작 시각입니다.
        start_time: 연구 성과를 계산할 포함 시작 시각입니다.
        end_time: 연구 성과를 계산할 배타적 종료 시각입니다.
        cron_interval_minutes: V4.1 연구에서 가정할 봇 실행 간격(분)입니다.

    Returns:
        후보들이 재사용할 RSI·추세·가격·크론 판단 시각 묶음입니다.
    """

    source_duration = pd.Timedelta(source_ohlcv.index.to_series().diff().dropna().min())
    event_times = source_ohlcv.index + source_duration
    rsi = pd.Series(index=event_times, dtype=float, name="RSI")
    previous_rsi = pd.Series(index=event_times, dtype=float, name="previous_RSI")
    trend_sma_by_period = {
        period: (
            pd.Series(index=event_times, dtype=float, name=f"trend_SMA_{period}"),
            pd.Series(index=event_times, dtype=float, name=f"previous_trend_SMA_{period}"),
        )
        for period in TREND_SMA_PERIODS
    }
    cron_duration = pd.Timedelta(minutes=cron_interval_minutes)
    evaluation_times: set[pd.Timestamp] = set()

    for position, (source_candle_start, _) in enumerate(source_ohlcv.iterrows()):
        signal_time = source_candle_start + source_duration
        strategy_ohlcv = build_strategy_ohlcv(
            source_ohlcv.iloc[: position + 1],
            V4_1_CONFIG.interval,
            strategy_candle_anchor,
        )
        if len(strategy_ohlcv) < V4_1_CONFIG.strategy.rsi_period + 2:
            continue
        rsi_series = calculate_rsi_series(strategy_ohlcv, period=V4_1_CONFIG.strategy.rsi_period)
        rsi.iloc[position] = float(rsi_series.iloc[-1])
        previous_rsi.iloc[position] = float(rsi_series.iloc[-2])
        for period, (trend_sma, previous_trend_sma) in trend_sma_by_period.items():
            if len(strategy_ohlcv) < period + 1:
                continue
            sma_series = strategy_ohlcv["close"].rolling(period).mean()
            trend_sma.iloc[position] = float(sma_series.iloc[-1])
            previous_trend_sma.iloc[position] = float(sma_series.iloc[-2])
        if (
            position < len(source_ohlcv) - 1
            and start_time <= signal_time < end_time
            and (signal_time - signal_time.normalize()) % cron_duration == pd.Timedelta(0)
        ):
            evaluation_times.add(signal_time)

    visible_mask = (event_times >= start_time) & (event_times < end_time)
    close_prices = pd.Series(source_ohlcv["close"].to_numpy(), index=event_times, name="close").loc[visible_mask]
    execution_opens = pd.Series(
        source_ohlcv["open"].shift(-1).to_numpy(),
        index=event_times,
        name="execution_open",
    ).loc[visible_mask]
    return ResearchSnapshots(
        rsi=rsi.loc[visible_mask],
        previous_rsi=previous_rsi.loc[visible_mask],
        close_prices=close_prices,
        execution_opens=execution_opens,
        trend_sma_by_period={
            period: (trend_sma.loc[visible_mask], previous_trend_sma.loc[visible_mask])
            for period, (trend_sma, previous_trend_sma) in trend_sma_by_period.items()
        },
        evaluation_times=evaluation_times,
        source_duration=source_duration,
    )


def simulate_candidate(
    snapshots: ResearchSnapshots,
    candidate: CandidateConfig,
    initial_capital: float = 1_000_000.0,
    fee_rate: float = 0.0005,
    base_trade_config: TradeConfig = V4_1_CONFIG.strategy.trade,
) -> CandidateResult:
    """후보를 V4.1과 같은 체결 가정으로 시뮬레이션하고 모든 원본 봉에서 낙폭을 계산합니다.

    Args:
        snapshots: 미리 계산한 현재·이전 RSI, 추세, 원본 봉 가격, 크론 시각입니다.
        candidate: 비교할 추세 필터·쿨다운·매수 비중·손익 관리 후보입니다.
        initial_capital: 시뮬레이션 시작 원화입니다.
        fee_rate: 매수·매도 주문에 각각 적용할 수수료 비율입니다.
        base_trade_config: 티커 공통 RSI 기준과 최소 주문 금액을 가져올 V4.1 기준 설정입니다.

    Returns:
        후보의 총수익률, 모든 원본 봉 종가 기준 최대 낙폭, 체결 횟수입니다.
    """

    trade_config = replace(
        base_trade_config,
        require_uptrend=candidate.require_uptrend,
        trend_sma_period=candidate.trend_sma_period,
        cooldown_hours=candidate.cooldown_hours,
        buy_ratio=candidate.buy_ratio,
        take_profit_pct=candidate.take_profit_pct,
        stop_loss_pct=candidate.stop_loss_pct,
    )
    cash = initial_capital
    coin_amount = 0.0
    average_buy_price = 0.0
    last_stop_loss_time: datetime | None = None
    peak_equity = initial_capital
    max_drawdown_pct = 0.0
    trades = 0

    for timestamp in snapshots.close_prices.index:
        current_price = float(snapshots.close_prices.loc[timestamp])
        equity = cash + coin_amount * current_price
        peak_equity = max(peak_equity, equity)
        max_drawdown_pct = min(max_drawdown_pct, (equity / peak_equity - 1) * 100)

        if timestamp not in snapshots.evaluation_times:
            continue
        rsi = float(snapshots.rsi.loc[timestamp])
        previous_rsi = float(snapshots.previous_rsi.loc[timestamp])
        trend_sma_series, previous_trend_sma_series = snapshots.trend_sma_by_period[candidate.trend_sma_period]
        trend_sma = float(trend_sma_series.loc[timestamp])
        previous_trend_sma = float(previous_trend_sma_series.loc[timestamp])
        execution_price = float(snapshots.execution_opens.loc[timestamp])
        required_values = (rsi, previous_rsi, execution_price)
        if candidate.require_uptrend:
            required_values += (trend_sma, previous_trend_sma)
        if any(isnan(value) for value in required_values):
            continue
        if execution_price <= 0:
            continue

        signal = SignalSnapshot(rsi, previous_rsi, current_price, trend_sma, previous_trend_sma)
        decision = decide_trade(
            signal,
            cash,
            coin_amount,
            average_buy_price,
            timestamp.to_pydatetime(),
            last_stop_loss_time,
            trade_config,
        )
        if decision.action == "WAIT":
            continue

        if decision.action == "BUY":
            order_amount = min(decision.order_amount, cash)
            bought_amount = order_amount * (1 - fee_rate) / execution_price
            if bought_amount <= 0:
                continue
            total_cost = average_buy_price * coin_amount + order_amount
            cash -= order_amount
            coin_amount += bought_amount
            average_buy_price = total_cost / coin_amount
        else:
            order_amount = min(decision.order_amount, coin_amount)
            if order_amount <= 0:
                continue
            cash += order_amount * execution_price * (1 - fee_rate)
            coin_amount -= order_amount
            if coin_amount <= 0:
                coin_amount = 0.0
                average_buy_price = 0.0
            if decision.action == "SELL_STOP_LOSS":
                last_stop_loss_time = (timestamp + snapshots.source_duration).to_pydatetime()
        trades += 1

    final_equity = cash + coin_amount * float(snapshots.close_prices.iloc[-1])
    return CandidateResult(
        config=candidate,
        total_return_pct=(final_equity / initial_capital - 1) * 100,
        max_drawdown_pct=max_drawdown_pct,
        trades=trades,
    )


def find_candidates(snapshots: ResearchSnapshots) -> list[CandidateResult]:
    """작은 후보 격자에서 수익률이 높고 최대 낙폭이 작은 순서로 결과를 반환합니다.

    Args:
        snapshots: 모든 후보가 공통으로 사용할 V4.1 연구 입력값입니다.

    Returns:
        최소 4회·최대 80회 체결한 후보를 수익률 내림차순, 낙폭 오름차순으로 정렬한 결과입니다.
    """

    results: list[CandidateResult] = []
    for require_uptrend in (False, True):
        trend_periods = TREND_SMA_PERIODS if require_uptrend else (V4_1_CONFIG.strategy.trade.trend_sma_period,)
        for trend_sma_period in trend_periods:
            for cooldown_hours in (0, 12, 24, 48):
                for buy_ratio in (0.5, 1.0):
                    for take_profit_pct in (3.0, 5.0):
                        for stop_loss_pct in (5.0, 10.0):
                            candidate = CandidateConfig(
                                require_uptrend,
                                trend_sma_period,
                                cooldown_hours,
                                buy_ratio,
                                take_profit_pct,
                                stop_loss_pct,
                            )
                            result = simulate_candidate(snapshots, candidate)
                            if 4 <= result.trades <= 80:
                                results.append(result)
    return sorted(results, key=lambda result: (-result.total_return_pct, -result.max_drawdown_pct))


def parse_args() -> argparse.Namespace:
    """V4.1 연구 대상 기간과 출력할 후보 개수를 CLI에서 읽습니다.

    Returns:
        기간·크론 가정·출력 개수를 담은 명령행 인자입니다.
    """

    parser = argparse.ArgumentParser(description="Screen V4.1 trend and cooldown candidates on cached OHLCV data.")
    parser.add_argument("--from", dest="start_date", default="2026-01-01", help="성과 계산 시작일(YYYY-MM-DD)")
    parser.add_argument("--to", dest="end_date", default="2026-08-02", help="성과 계산 종료일(YYYY-MM-DD, 포함)")
    parser.add_argument("--cron-interval-minutes", type=int, default=60, help="가정할 crontab 실행 간격(분)")
    parser.add_argument("--top", type=int, default=10, help="출력할 상위 후보 개수")
    return parser.parse_args()


def main() -> None:
    """캐시된 ETH 원본 봉으로 V4.1 후보 연구 결과를 출력합니다."""

    args = parse_args()
    start_time = pd.Timestamp(args.start_date)
    end_time = pd.Timestamp(args.end_date) + pd.Timedelta(days=1)
    source_interval = select_source_interval(args.cron_interval_minutes)
    source_ohlcv = load_cached_ohlcv(DEFAULT_CACHE_DIR, V4_1_CONFIG.ticker, source_interval)
    anchor = get_cached_strategy_anchor(DEFAULT_CACHE_DIR, V4_1_CONFIG.ticker, source_interval, V4_1_CONFIG.interval)
    if source_ohlcv.empty or anchor is None:
        raise SystemExit(f"V3 {source_interval} cache and {V4_1_CONFIG.interval} anchor are required. Run the V3 backtest first.")

    snapshots = build_research_snapshots(
        source_ohlcv,
        anchor,
        start_time,
        end_time,
        args.cron_interval_minutes,
    )
    candidates = find_candidates(snapshots)
    for rank, result in enumerate(candidates[: args.top], start=1):
        config = result.config
        trend = "on" if config.require_uptrend else "off"
        print(
            f"{rank}. return={result.total_return_pct:.2f}% drawdown={result.max_drawdown_pct:.2f}% "
            f"trades={result.trades} trend={trend} SMA={config.trend_sma_period} cooldown={config.cooldown_hours}h "
            f"buy_ratio={config.buy_ratio:g} take_profit={config.take_profit_pct:g}% "
            f"stop_loss={config.stop_loss_pct:g}%"
        )


if __name__ == "__main__":
    main()
