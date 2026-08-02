"""V4.1 백테스트 결과를 PNG로 저장하는 실행 도구입니다."""

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
from develop.v4_1.backtesting.backtest_logic import (  # noqa: E402
    BacktestResult,
    calculate_period_source_count,
    run_backtest,
    select_source_interval,
)
from develop.v4_1.config import V4_1_CONFIG, V4_1Config, interval_to_timedelta  # noqa: E402


def format_backtest_summary(result: BacktestResult) -> str:
    """V4.1 PNG 제목 둘째 줄의 원금·체결·자산·수익률 요약을 만듭니다.

    Args:
        result: V4.1 순수 백테스트 결과입니다.

    Returns:
        사람이 읽기 쉬운 한 줄 결과 요약입니다.
    """

    return " | ".join(
        [
            f"initial capital: {result.initial_capital:,.0f} KRW",
            f"trades: {len(result.trades)}",
            f"final equity: {result.final_equity:,.0f} KRW",
            f"total return: {result.total_return_pct:.2f}%",
        ]
    )


def plot_backtest(
    result: BacktestResult,
    output_path: Path,
    config: V4_1Config = V4_1_CONFIG,
    show_rsi_trade_points: bool = False,
) -> None:
    """V4.1 가격·RSI·자산 곡선과 실제 가상 체결 지점을 PNG로 저장합니다.

    Args:
        result: 순수 V4.1 백테스트가 계산한 가격, RSI, 자산, 체결 기록입니다.
        output_path: 생성할 PNG 파일 경로입니다.
        config: 제목·RSI 기준선·수수료 표시에 사용할 V4.1 설정입니다.
        show_rsi_trade_points: ``True``면 실제 체결과 같은 RSI 지점에 색 점을 표시합니다.
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
    trade = config.strategy.trade
    strategy_line = " | ".join(
        [
            config.ticker,
            config.interval,
            f"RSI({config.strategy.rsi_period}) recovery buy {trade.buy_threshold:g}",
            f"trend price ≥ SMA({trade.trend_sma_period})",
            f"cooldown {trade.cooldown_hours}h",
        ]
    )
    execution_line = " | ".join(
        [
            f"sell ≥ {trade.sell_threshold:g}",
            f"take profit ≥ {trade.take_profit_pct:g}%",
            f"stop loss ≤ -{trade.stop_loss_pct:g}%",
            f"fee {config.backtest.fee_rate * 100:.02f}%",
            f"cron assumption {config.backtest.cron_interval_minutes}m",
            f"period {result.close_prices.index[0]:%Y-%m-%d} ~ {result.close_prices.index[-1]:%Y-%m-%d}",
        ]
    )
    figure.suptitle(f"{strategy_line}\n{execution_line}\n{format_backtest_summary(result)}")

    price_axis.plot(result.close_prices.index, result.close_prices, label="close", color="black", linewidth=1)
    marker_config = {
        "BUY": ("^", "tab:blue", "buy"),
        "SELL_STOP_LOSS": ("v", "tab:red", "stop loss"),
        "SELL_TAKE_PROFIT": ("v", "tab:green", "take profit"),
        "SELL_RSI": ("v", "tab:purple", "RSI exit"),
    }
    for action, (marker, color, label) in marker_config.items():
        action_trades = [trade_record for trade_record in result.trades if trade_record.action == action]
        if action_trades:
            price_axis.scatter(
                [trade_record.execution_time for trade_record in action_trades],
                [trade_record.execution_price for trade_record in action_trades],
                marker=marker,
                color=color,
                s=70,
                label=label,
                zorder=3,
            )
    price_axis.set_ylabel("Price (KRW)")
    price_axis.set_title("Price and simulated V4.1 executions")
    price_axis.legend(loc="best")
    price_axis.grid(alpha=0.25)

    rsi_axis.plot(result.rsi.index, result.rsi, label=f"RSI({config.strategy.rsi_period})", color="tab:purple")
    rsi_axis.axhline(trade.buy_threshold, color="tab:blue", linestyle="--", label="buy recovery threshold")
    rsi_axis.axhline(trade.sell_threshold, color="tab:red", linestyle="--", label="sell threshold")
    if show_rsi_trade_points:
        buy_trades = [trade_record for trade_record in result.trades if trade_record.action == "BUY"]
        sell_trades = [trade_record for trade_record in result.trades if trade_record.action.startswith("SELL_")]
        buy_points = result.rsi.reindex([trade_record.signal_time for trade_record in buy_trades]).dropna()
        sell_points = result.rsi.reindex([trade_record.signal_time for trade_record in sell_trades]).dropna()
        rsi_axis.scatter(buy_points.index, buy_points, color="tab:blue", s=24, label="executed buy", zorder=3)
        rsi_axis.scatter(sell_points.index, sell_points, color="tab:red", s=24, label="executed sell", zorder=3)
    rsi_axis.set_ylabel("RSI")
    rsi_axis.set_ylim(0, 100)
    rsi_axis.legend(loc="best")
    rsi_axis.grid(alpha=0.25)

    equity_axis.plot(result.equity_curve.index, result.equity_curve, label="equity", color="tab:orange")
    equity_axis.set_ylabel("Equity (KRW)")
    equity_axis.set_xlabel("Time")
    equity_axis.legend(loc="best")
    equity_axis.grid(alpha=0.25)

    figure.tight_layout(rect=(0, 0, 1, 0.89))
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def parse_period(start_date: str, end_date: str | None) -> tuple[pd.Timestamp, pd.Timestamp | None]:
    """CLI 날짜를 포함 시작·배타적 종료 시각으로 변환합니다.

    Args:
        start_date: 백테스트에 포함할 시작 날짜입니다. ``YYYY-MM-DD`` 형식입니다.
        end_date: 백테스트에 포함할 마지막 날짜입니다. ``YYYY-MM-DD`` 형식입니다.

    Returns:
        시작일 자정과 종료일 다음 날 자정의 튜플입니다.

    Raises:
        ValueError: 날짜 형식이나 기간 순서가 잘못됐을 때 발생합니다.
    """

    try:
        start_time = pd.Timestamp(start_date).normalize()
        end_time = pd.Timestamp(end_date).normalize() + pd.Timedelta(days=1) if end_date else None
    except (TypeError, ValueError) as error:
        raise ValueError("--from and --to must use YYYY-MM-DD format.") from error
    if end_time is not None and end_time <= start_time:
        raise ValueError("--to must be the same date as or later than --from.")
    return start_time, end_time


def parse_args() -> argparse.Namespace:
    """V4.1 기간·크론·RSI 체결 점·PNG 경로 CLI 인자를 읽습니다.

    Returns:
        V4.1 백테스트 실행에 필요한 명령행 인자입니다.
    """

    parser = argparse.ArgumentParser(description="Visualize V4.1 trade logic on historical OHLCV data.")
    parser.add_argument("--from", dest="start_date", default="2026-01-01", help="포함할 시작 날짜(YYYY-MM-DD)")
    parser.add_argument("--to", dest="end_date", help="포함할 마지막 날짜(YYYY-MM-DD)")
    parser.add_argument(
        "--cron-interval-minutes",
        type=int,
        default=V4_1_CONFIG.backtest.cron_interval_minutes,
        help="백테스트에서 가정할 crontab 실행 간격(분)",
    )
    parser.add_argument(
        "--show-rsi-trade-points",
        action="store_true",
        help="실제 체결한 매수·매도 주문의 RSI 지점에 색 점을 표시합니다.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("v4_1_backtest.png"),
        help="생성할 PNG 파일 경로입니다.",
    )
    return parser.parse_args()


def main() -> None:
    """원본 OHLCV 캐시를 보완하고 V4.1 백테스트 PNG와 요약 결과를 생성합니다."""

    args = parse_args()
    try:
        simulation_start, simulation_end = parse_period(args.start_date, args.end_date)
    except ValueError as error:
        raise SystemExit(f"Invalid backtest period: {error}") from error

    config = replace(
        V4_1_CONFIG,
        backtest=replace(V4_1_CONFIG.backtest, cron_interval_minutes=args.cron_interval_minutes),
    )
    source_interval = select_source_interval(config.backtest.cron_interval_minutes)
    source_duration = pd.Timedelta(interval_to_timedelta(source_interval))
    cached_ohlcv = load_cached_ohlcv(DEFAULT_CACHE_DIR, config.ticker, source_interval)
    now = pd.Timestamp.now()
    requested_end = simulation_end or now
    if requested_end >= now:
        if cached_ohlcv.empty:
            requested_end = get_ohlcv(config.ticker, interval=source_interval, count=1).index[-1]
        else:
            cache_anchor = cached_ohlcv.index[0]
            requested_end = cache_anchor + (now - cache_anchor).floor(source_duration)
    if requested_end <= simulation_start:
        raise SystemExit("Invalid backtest period: no completed source candles exist after --from.")

    source_count = calculate_period_source_count(
        simulation_start,
        requested_end,
        source_interval,
        config.interval,
        config.strategy.rsi_period,
    )
    requested_range = OhlcvRange(requested_end - source_duration * source_count, requested_end)
    coverage_ranges = load_coverage_ranges(
        DEFAULT_CACHE_DIR,
        config.ticker,
        source_interval,
        cached_ohlcv,
        source_duration,
    )
    missing_ranges = find_uncovered_ranges(coverage_ranges, requested_range)
    ohlcv = get_or_fetch_cached_ohlcv(
        config.ticker,
        source_interval,
        requested_range,
        source_duration,
        lambda ticker, interval, count, to: get_ohlcv(ticker, interval=interval, count=count, to=to),
    )
    strategy_anchor = get_cached_strategy_anchor(
        DEFAULT_CACHE_DIR,
        config.ticker,
        source_interval,
        config.interval,
    )
    if strategy_anchor is None:
        strategy_anchor = get_ohlcv(config.ticker, interval=config.interval, count=1, to=requested_end).index[-1]
        save_strategy_anchor(DEFAULT_CACHE_DIR, config.ticker, source_interval, config.interval, strategy_anchor)

    result_end = min(simulation_end, requested_end) if simulation_end is not None else None
    result = run_backtest(ohlcv, config, strategy_anchor, simulation_start, result_end)
    plot_backtest(result, args.output, config, args.show_rsi_trade_points)
    equity = result.equity_curve
    max_drawdown_pct = float((equity / equity.cummax() - 1).min() * 100)
    print(f"output: {args.output}")
    print(f"source interval: {source_interval}")
    print(f"cache API ranges: {len(missing_ranges)}")
    print(f"period: {simulation_start:%Y-%m-%d} ~ {result.close_prices.index[-1]:%Y-%m-%d}")
    print(f"cron assumption: every {config.backtest.cron_interval_minutes} minutes")
    print(f"trades: {len(result.trades)}")
    print(f"final equity: {result.final_equity:,.0f} KRW")
    print(f"total return: {result.total_return_pct:.2f}%")
    print(f"max drawdown: {max_drawdown_pct:.2f}%")


if __name__ == "__main__":
    main()
