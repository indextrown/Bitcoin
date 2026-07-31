"""V3 trade_logic을 과거 캔들에 적용해 백테스트 그래프를 만드는 도구입니다.

신호는 캔들이 마감된 시점의 RSI로 판단하고, 주문은 다음 캔들의 시가에 체결된다고
가정합니다. 따라서 현재 캔들의 종가를 미리 안 것처럼 계산하는 오류를 피합니다.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.upbit_develop_library import calculate_rsi_series, get_ohlcv  # noqa: E402
from develop.v3.trade_logic import TradeConfig, decide_trade  # noqa: E402


@dataclass(frozen=True)
class BacktestTrade:
    action: str
    signal_time: pd.Timestamp
    execution_time: pd.Timestamp
    execution_price: float
    order_amount: float
    profit_rate: float


@dataclass(frozen=True)
class BacktestResult:
    initial_capital: float
    final_equity: float
    total_return_pct: float
    rsi: pd.Series
    equity_curve: pd.Series
    trades: list[BacktestTrade]


def validate_ohlcv(ohlcv: pd.DataFrame) -> None:
    """백테스트에 필요한 OHLCV 컬럼과 최소 데이터 수를 확인합니다."""

    required_columns = {"open", "close"}
    missing_columns = required_columns - set(ohlcv.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"OHLCV data is missing required columns: {missing}")
    if len(ohlcv) < 16:
        raise ValueError("At least 16 OHLCV rows are required for RSI(14) backtesting.")


def run_backtest(
    ohlcv: pd.DataFrame,
    initial_capital: float = 1_000_000.0,
    fee_rate: float = 0.0005,
    config: TradeConfig = TradeConfig(),
) -> BacktestResult:
    """V3 판단 로직을 과거 데이터에 적용해 가상 자산과 체결 기록을 반환합니다."""

    validate_ohlcv(ohlcv)
    if initial_capital <= 0:
        raise ValueError("initial_capital must be greater than zero.")
    if not 0 <= fee_rate < 1:
        raise ValueError("fee_rate must be between 0 (inclusive) and 1 (exclusive).")

    prices = ohlcv.copy()
    rsi = calculate_rsi_series(prices, period=14)
    cash = initial_capital
    coin_amount = 0.0
    avg_buy_price = 0.0
    trades: list[BacktestTrade] = []
    equity_values: list[float] = []

    for position, (signal_time, candle) in enumerate(prices.iterrows()):
        current_price = float(candle["close"])
        equity_values.append(cash + coin_amount * current_price)

        if position >= len(prices) - 1:
            continue

        rsi_value = float(rsi.iloc[position])
        if pd.isna(rsi_value):
            continue

        decision = decide_trade(
            rsi_value,
            cash,
            coin_amount,
            avg_buy_price,
            current_price,
            config,
        )
        if decision.action == "WAIT":
            continue

        execution_candle = prices.iloc[position + 1]
        execution_time = prices.index[position + 1]
        execution_price = float(execution_candle["open"])
        if execution_price <= 0:
            continue

        if decision.action == "BUY":
            order_amount = min(decision.order_amount, cash)
            bought_amount = order_amount * (1 - fee_rate) / execution_price
            if bought_amount <= 0:
                continue

            total_cost = avg_buy_price * coin_amount + order_amount
            cash -= order_amount
            coin_amount += bought_amount
            avg_buy_price = total_cost / coin_amount
        else:
            order_amount = min(decision.order_amount, coin_amount)
            if order_amount <= 0:
                continue

            cash += order_amount * execution_price * (1 - fee_rate)
            coin_amount -= order_amount
            if coin_amount <= 0:
                coin_amount = 0.0
                avg_buy_price = 0.0

        trades.append(
            BacktestTrade(
                action=decision.action,
                signal_time=signal_time,
                execution_time=execution_time,
                execution_price=execution_price,
                order_amount=order_amount,
                profit_rate=decision.profit_rate,
            )
        )

    equity_curve = pd.Series(equity_values, index=prices.index, name="equity")
    final_equity = float(equity_curve.iloc[-1])
    total_return_pct = (final_equity / initial_capital - 1) * 100
    return BacktestResult(
        initial_capital=initial_capital,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        rsi=rsi,
        equity_curve=equity_curve,
        trades=trades,
    )


def plot_backtest(
    ohlcv: pd.DataFrame,
    result: BacktestResult,
    output_path: Path,
    config: TradeConfig = TradeConfig(),
) -> None:
    """가격·RSI·자산 곡선과 V3 거래 지점을 한 PNG 파일로 저장합니다."""

    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, (price_axis, rsi_axis, equity_axis) = plt.subplots(
        3,
        1,
        figsize=(15, 12),
        sharex=True,
        height_ratios=[2, 1, 1],
    )

    price_axis.plot(ohlcv.index, ohlcv["close"], label="close", color="black", linewidth=1)
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
    price_axis.set_title("V3 trade logic backtest")
    price_axis.legend(loc="best")
    price_axis.grid(alpha=0.25)

    rsi_axis.plot(result.rsi.index, result.rsi, label="RSI(14)", color="tab:purple")
    rsi_axis.axhline(config.buy_threshold, color="tab:blue", linestyle="--", label="buy threshold")
    rsi_axis.axhline(config.sell_threshold, color="tab:red", linestyle="--", label="sell threshold")
    rsi_axis.set_ylabel("RSI")
    rsi_axis.set_ylim(0, 100)
    rsi_axis.legend(loc="best")
    rsi_axis.grid(alpha=0.25)

    equity_axis.plot(result.equity_curve.index, result.equity_curve, label="equity", color="tab:orange")
    equity_axis.set_ylabel("Equity (KRW)")
    equity_axis.set_xlabel("Time")
    equity_axis.legend(loc="best")
    equity_axis.grid(alpha=0.25)

    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize V3 trade logic on historical OHLCV data.")
    parser.add_argument("--ticker", default="KRW-ETH")
    parser.add_argument("--interval", default="minute240")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--fee-rate", type=float, default=0.0005)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("v3_backtest.png"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ohlcv = get_ohlcv(args.ticker, interval=args.interval, count=args.count)
    result = run_backtest(ohlcv, args.initial_capital, args.fee_rate)
    plot_backtest(ohlcv, result, args.output)
    print(f"output: {args.output}")
    print(f"trades: {len(result.trades)}")
    print(f"final equity: {result.final_equity:,.0f} KRW")
    print(f"total return: {result.total_return_pct:.2f}%")


if __name__ == "__main__":
    main()
