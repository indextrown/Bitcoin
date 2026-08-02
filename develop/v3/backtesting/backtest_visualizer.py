"""V3 백테스트 결과를 조회하고 PNG 그래프로 저장하는 실행 도구입니다."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.upbit_develop_library import get_ohlcv  # noqa: E402
from develop.v3.backtesting.backtest_logic import (  # noqa: E402
    BacktestResult,
    calculate_period_source_count,
    calculate_source_count,
    run_backtest,
    select_source_interval,
)
from develop.v3.backtesting.ohlcv_cache import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    OhlcvRange,
    find_uncovered_ranges,
    get_cached_strategy_anchor,
    get_or_fetch_cached_ohlcv,
    load_coverage_ranges,
    load_cached_ohlcv,
    save_strategy_anchor,
)
from develop.v3.config import V3_CONFIG, V3Config, interval_to_timedelta  # noqa: E402


def plot_backtest(
    result: BacktestResult,
    output_path: Path,
    config: V3Config = V3_CONFIG,
) -> None:
    """가격·RSI·자산 곡선과 설정값을 한 PNG 파일로 저장합니다.

    Args:
        result: 순수 백테스트가 계산한 가격, RSI, 자산 곡선, 체결 기록입니다.
        output_path: 생성할 PNG 파일의 전체 또는 상대 경로입니다.
        config: 제목·RSI 기준선·수수료 표시에 사용할 V3 설정입니다.
    """

    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, (price_axis, rsi_axis, equity_axis) = plt.subplots(
        3,
        1,
        figsize=(15, 12),
        sharex=True,
        height_ratios=[2, 1, 1],
    )
    figure.suptitle(
        " | ".join(
            [
                config.ticker,
                config.interval,
                f"RSI({config.strategy.rsi_period})",
                f"buy ≤ {config.strategy.trade.buy_threshold:g}",
                f"sell ≥ {config.strategy.trade.sell_threshold:g}",
                f"take profit ≥ {config.strategy.trade.sell_profit_pct:g}%",
                f"fee {config.backtest.fee_rate * 100:.02f}%",
                f"cron assumption {config.backtest.cron_interval_minutes}m",
                f"period {result.close_prices.index[0]:%Y-%m-%d} ~ {result.close_prices.index[-1]:%Y-%m-%d}",
            ]
        )
    )

    price_axis.plot(
        result.close_prices.index,
        result.close_prices,
        label="close",
        color="black",
        linewidth=1,
    )
    marker_config = {
        "BUY": ("^", "tab:blue", "buy"),
        "SELL_LOSS": ("v", "tab:red", "sell at break-even/loss"),
        "SELL_PROFIT": ("v", "tab:green", "sell at profit"),
    }
    for action, (marker, color, label) in marker_config.items():
        action_trades = [trade for trade in result.trades if trade.action == action]
        if not action_trades:
            continue
        price_axis.scatter(
            [trade.execution_time for trade in action_trades],
            [trade.execution_price for trade in action_trades],
            marker=marker,
            color=color,
            s=70,
            label=label,
            zorder=3,
        )
    price_axis.set_ylabel("Price (KRW)")
    price_axis.set_title("Price and simulated trade executions")
    price_axis.legend(loc="best")
    price_axis.grid(alpha=0.25)

    rsi_axis.plot(
        result.rsi.index,
        result.rsi,
        label=f"RSI({config.strategy.rsi_period})",
        color="tab:purple",
    )
    rsi_axis.axhline(
        config.strategy.trade.buy_threshold,
        color="tab:blue",
        linestyle="--",
        label="buy threshold",
    )
    rsi_axis.axhline(
        config.strategy.trade.sell_threshold,
        color="tab:red",
        linestyle="--",
        label="sell threshold",
    )
    rsi_axis.set_ylabel("RSI")
    rsi_axis.set_ylim(0, 100)
    rsi_axis.legend(loc="best")
    rsi_axis.grid(alpha=0.25)

    equity_axis.plot(result.equity_curve.index, result.equity_curve, label="equity", color="tab:orange")
    equity_axis.set_ylabel("Equity (KRW)")
    equity_axis.set_xlabel("Time")
    equity_axis.legend(loc="best")
    equity_axis.grid(alpha=0.25)

    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def parse_backtest_period(
    start_date: str | None,
    end_date: str | None,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """날짜 문자열을 백테스트의 시작 시각과 배타적 종료 시각으로 변환합니다.

    Args:
        start_date: 포함할 시작 날짜입니다. ``YYYY-MM-DD`` 형식이며, ``None``이면
            기존 ``--count`` 방식으로 최근 데이터를 조회합니다.
        end_date: 포함할 마지막 날짜입니다. ``YYYY-MM-DD`` 형식이며, ``None``이면
            최신 데이터까지 조회합니다.

    Returns:
        시작일 00:00과 종료일 다음 날 00:00으로 구성된 ``(start, end_exclusive)``
        튜플입니다. 시작일이 없으면 ``(None, None)``을 반환합니다.

    Raises:
        ValueError: 날짜 형식이 잘못됐거나 종료일이 시작일보다 빠를 때 발생합니다.
    """

    if start_date is None:
        if end_date is not None:
            raise ValueError("--to requires --from.")
        return None, None

    try:
        start_time = pd.Timestamp(start_date)
        end_day = pd.Timestamp(end_date) if end_date is not None else None
    except (TypeError, ValueError) as error:
        raise ValueError("--from and --to must use YYYY-MM-DD format.") from error

    if start_time != start_time.normalize() or (end_day is not None and end_day != end_day.normalize()):
        raise ValueError("--from and --to must use YYYY-MM-DD format.")

    start_time = start_time.normalize()
    end_time = end_day.normalize() + pd.Timedelta(days=1) if end_day is not None else None
    if end_time is not None and end_time <= start_time:
        raise ValueError("--to must be the same date as or later than --from.")
    return start_time, end_time


def parse_args() -> argparse.Namespace:
    """공용 V3 설정을 기본값으로 사용하는 시각화 실행 인자를 읽습니다.

    Returns:
        티커, 전략 봉, 조회 개수, 기간, 자금, 수수료, 크론 가정, PNG 경로를 담은 인자입니다.
    """

    parser = argparse.ArgumentParser(description="Visualize V3 trade logic on historical OHLCV data.")
    parser.add_argument("--ticker", default=V3_CONFIG.ticker, help="분석할 업비트 마켓 티커입니다.")
    parser.add_argument("--interval", default=V3_CONFIG.interval, help="RSI 전략이 사용할 업비트 캔들 간격입니다.")
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="기간을 지정하지 않았을 때 그래프에 사용할 전략 봉의 목표 개수입니다.",
    )
    parser.add_argument(
        "--from",
        dest="start_date",
        help="포함할 시작 날짜입니다. YYYY-MM-DD 형식입니다.",
    )
    parser.add_argument(
        "--to",
        dest="end_date",
        help="포함할 마지막 날짜입니다. YYYY-MM-DD 형식이며 --from과 함께 사용합니다.",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=V3_CONFIG.backtest.initial_capital,
        help="백테스트 시작 원화 자산입니다.",
    )
    parser.add_argument(
        "--fee-rate",
        type=float,
        default=V3_CONFIG.backtest.fee_rate,
        help="매수·매도 주문마다 적용할 수수료 비율입니다. (0.0005 = 0.05%%)",
    )
    parser.add_argument(
        "--cron-interval-minutes",
        type=int,
        default=V3_CONFIG.backtest.cron_interval_minutes,
        help="백테스트에서 가정할 crontab 실행 간격(분)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("v3_backtest.png"),
        help="생성할 PNG 파일 경로입니다.",
    )
    return parser.parse_args()


def main() -> None:
    """과거 OHLCV를 조회하고 V3 백테스트 PNG와 요약 결과를 생성합니다.

    CLI 인자로 공용 설정의 일부를 덮어쓴 뒤, 크론 가정에 맞는 원본 봉과 업비트의
    실제 전략 봉 시작 시각을 조회합니다. 이 함수는 네트워크 호출과 PNG 파일 저장을
    담당하며, 순수 매매 판단은 ``run_backtest``에 맡깁니다.
    """

    args = parse_args()
    try:
        simulation_start, simulation_end = parse_backtest_period(args.start_date, args.end_date)
    except ValueError as error:
        raise SystemExit(f"Invalid backtest period: {error}") from error
    runtime_config = replace(
        V3_CONFIG,
        ticker=args.ticker,
        interval=args.interval,
        backtest=replace(
            V3_CONFIG.backtest,
            initial_capital=args.initial_capital,
            fee_rate=args.fee_rate,
            cron_interval_minutes=args.cron_interval_minutes,
        ),
    )
    source_interval = select_source_interval(runtime_config.backtest.cron_interval_minutes)
    source_duration = pd.Timedelta(interval_to_timedelta(source_interval))
    now = pd.Timestamp.now()
    cached_ohlcv = load_cached_ohlcv(DEFAULT_CACHE_DIR, runtime_config.ticker, source_interval)
    requested_end = simulation_end or now
    if requested_end >= now:
        if cached_ohlcv.empty:
            current_source_candle = get_ohlcv(
                runtime_config.ticker,
                interval=source_interval,
                count=1,
            )
            requested_end = current_source_candle.index[-1]
        else:
            cache_anchor = cached_ohlcv.index[0]
            requested_end = cache_anchor + (now - cache_anchor).floor(source_duration)

    if simulation_start is not None and requested_end <= simulation_start:
        raise SystemExit("Invalid backtest period: no completed source candles exist after --from.")

    if simulation_start is None:
        source_count = calculate_source_count(runtime_config.interval, source_interval, args.count)
    else:
        source_count = calculate_period_source_count(
            simulation_start,
            requested_end,
            source_interval,
            runtime_config.interval,
            runtime_config.strategy.rsi_period,
        )

    requested_start = requested_end - source_duration * source_count
    requested_range = OhlcvRange(requested_start, requested_end)
    cached_coverage_ranges = load_coverage_ranges(
        DEFAULT_CACHE_DIR,
        runtime_config.ticker,
        source_interval,
        cached_ohlcv,
        source_duration,
    )
    cache_miss_ranges = find_uncovered_ranges(cached_coverage_ranges, requested_range)
    ohlcv = get_or_fetch_cached_ohlcv(
        runtime_config.ticker,
        source_interval,
        requested_range,
        source_duration,
        lambda ticker, interval, count, to: get_ohlcv(ticker, interval=interval, count=count, to=to),
    )

    strategy_candle_anchor = get_cached_strategy_anchor(
        DEFAULT_CACHE_DIR,
        runtime_config.ticker,
        source_interval,
        runtime_config.interval,
    )
    if strategy_candle_anchor is None:
        strategy_ohlcv = get_ohlcv(
            runtime_config.ticker,
            interval=runtime_config.interval,
            count=1,
            to=requested_end,
        )
        strategy_candle_anchor = strategy_ohlcv.index[-1]
        save_strategy_anchor(
            DEFAULT_CACHE_DIR,
            runtime_config.ticker,
            source_interval,
            runtime_config.interval,
            strategy_candle_anchor,
        )

    result_end = min(simulation_end, requested_end) if simulation_end is not None else None
    result = run_backtest(
        ohlcv,
        runtime_config,
        strategy_candle_anchor,
        simulation_start,
        result_end,
    )
    plot_backtest(result, args.output, runtime_config)
    print(f"output: {args.output}")
    print(f"source interval: {source_interval}")
    print(f"cache: {DEFAULT_CACHE_DIR}")
    print(f"cache API ranges: {len(cache_miss_ranges)}")
    if simulation_start is not None:
        period_end_label = (simulation_end - pd.Timedelta(days=1)).strftime("%Y-%m-%d") if simulation_end else "latest"
        print(f"period: {simulation_start:%Y-%m-%d} ~ {period_end_label}")
    print(f"cron assumption: every {runtime_config.backtest.cron_interval_minutes} minutes")
    print(f"strategy candle anchor: {strategy_candle_anchor}")
    print(f"trades: {len(result.trades)}")
    print(f"final equity: {result.final_equity:,.0f} KRW")
    print(f"total return: {result.total_return_pct:.2f}%")


if __name__ == "__main__":
    main()
