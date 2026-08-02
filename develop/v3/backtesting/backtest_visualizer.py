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
    calculate_source_count,
    run_backtest,
    select_source_interval,
)
from develop.v3.config import V3_CONFIG, V3Config  # noqa: E402


def plot_backtest(
    ohlcv: pd.DataFrame,
    result: BacktestResult,
    output_path: Path,
    config: V3Config = V3_CONFIG,
) -> None:
    """가격·RSI·자산 곡선과 설정값을 한 PNG 파일로 저장합니다.

    Args:
        ohlcv: 크론 재현에 사용한 원본 OHLCV 데이터입니다. 가격 선을 그릴 때 사용합니다.
        result: 순수 백테스트가 계산한 RSI, 자산 곡선, 체결 기록입니다.
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
            ]
        )
    )

    price_axis.plot(
        result.equity_curve.index,
        ohlcv["close"],
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


def parse_args() -> argparse.Namespace:
    """공용 V3 설정을 기본값으로 사용하는 시각화 실행 인자를 읽습니다.

    Returns:
        티커, 전략 봉, 조회 개수, 자금, 수수료, 크론 가정, PNG 경로를 담은 인자입니다.
    """

    parser = argparse.ArgumentParser(description="Visualize V3 trade logic on historical OHLCV data.")
    parser.add_argument("--ticker", default=V3_CONFIG.ticker, help="분석할 업비트 마켓 티커입니다.")
    parser.add_argument("--interval", default=V3_CONFIG.interval, help="RSI 전략이 사용할 업비트 캔들 간격입니다.")
    parser.add_argument("--count", type=int, default=200, help="그래프에 사용할 전략 봉의 목표 개수입니다.")
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
    source_count = calculate_source_count(runtime_config.interval, source_interval, args.count)
    ohlcv = get_ohlcv(runtime_config.ticker, interval=source_interval, count=source_count)
    strategy_ohlcv = get_ohlcv(runtime_config.ticker, interval=runtime_config.interval, count=1)
    strategy_candle_anchor = strategy_ohlcv.index[-1]
    result = run_backtest(ohlcv, runtime_config, strategy_candle_anchor)
    plot_backtest(ohlcv, result, args.output, runtime_config)
    print(f"output: {args.output}")
    print(f"source interval: {source_interval}")
    print(f"cron assumption: every {runtime_config.backtest.cron_interval_minutes} minutes")
    print(f"strategy candle anchor: {strategy_candle_anchor}")
    print(f"trades: {len(result.trades)}")
    print(f"final equity: {result.final_equity:,.0f} KRW")
    print(f"total return: {result.total_return_pct:.2f}%")


if __name__ == "__main__":
    main()
