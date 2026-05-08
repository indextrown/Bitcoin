from __future__ import annotations

# ==========================
# V1 vs V2 백테스트 비교 도구
# ==========================
# 이 파일은 실거래 봇이 아니라 전략 성능 비교용 분석 스크립트입니다.
# 같은 티커, 같은 기간 데이터에서 V1과 V2 신호를 재생해서
# 최종 수익률, MDD, 승률, 거래 횟수, 자산곡선을 비교합니다.
#
# 기본 목적
# 1. V1이 너무 보수적인지 확인
# 2. V2가 실제로 더 자주 진입하는지 확인
# 3. 수익률만 아니라 낙폭(MDD)까지 같이 비교
# 4. 전략 튜닝 전후 성능 차이를 빠르게 확인
#
# 주의
# - 현재 버전은 단일 티커 비교용입니다.
# - 실거래 수수료를 단순 비율로 반영합니다.
# - 슬리피지, 호가 충격, 다종목 동시 운용은 단순화되어 있습니다.

"""V1, V2 전략의 핵심 신호를 같은 티커 구간에서 비교하는 간단 백테스트 도구.

이 스크립트는 실거래 봇이 아니라 전략 비교용 분석 도구입니다.
기존 실시간 스캐너 구조(get_top_coin_list, 다종목 동시 보유)는 단순화하고,
단일 티커에 대해 각 전략의 진입/청산 규칙이 어떤 결과를 내는지 빠르게
비교하는 데 초점을 둡니다.
"""

from dataclasses import dataclass
from pathlib import Path
import argparse
import math
import sys

import matplotlib.pyplot as plt
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.upbit_develop_library import get_ohlcv  # noqa: E402
from operate.v1.strategy_v1 import (  # noqa: E402
    StrategyConfig as StrategyV1Config,
    evaluate_entry_signal as evaluate_v1_entry_signal,
    evaluate_exit_signal as evaluate_v1_exit_signal,
    calculate_order_budget as calculate_v1_order_budget,
)
from operate.v2.strategy_v2 import (  # noqa: E402
    StrategyConfig as StrategyV2Config,
    evaluate_entry_signal as evaluate_v2_entry_signal,
    evaluate_exit_signal as evaluate_v2_exit_signal,
    calculate_order_budget as calculate_v2_order_budget,
)


@dataclass(frozen=True)
class Trade:
    side: str
    time: pd.Timestamp
    price: float
    quantity: float
    reason: str
    equity_after: float


@dataclass(frozen=True)
class BacktestResult:
    strategy_name: str
    ticker: str
    initial_capital: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    win_rate_pct: float
    trades: list[Trade]
    equity_curve: pd.Series


def build_balance_row(ticker: str, quantity: float, avg_buy_price: float) -> list[dict[str, str]]:
    """전략 함수 재사용을 위해 단일 보유 포지션을 잔고 형식으로 구성합니다."""

    _, currency = ticker.split("-", 1)
    return [
        {
            "currency": currency,
            "balance": f"{quantity}",
            "locked": "0",
            "avg_buy_price": f"{avg_buy_price}",
            "unit_currency": "KRW",
        }
    ]


def compute_max_drawdown_pct(equity_curve: pd.Series) -> float:
    """자산곡선에서 최대 낙폭(MDD)을 퍼센트로 계산합니다."""

    running_peak = equity_curve.cummax()
    drawdown = (equity_curve / running_peak - 1.0) * 100.0
    return float(drawdown.min()) if not drawdown.empty else 0.0


def compute_win_rate_pct(trades: list[Trade]) -> float:
    """완결된 매도 거래 기준 승률을 계산합니다."""

    entry_prices: list[float] = []
    wins = 0
    closed = 0

    for trade in trades:
        if trade.side == "buy":
            entry_prices.append(trade.price)
            continue

        if trade.side == "sell" and entry_prices:
            entry_price = entry_prices.pop(0)
            closed += 1
            if trade.price > entry_price:
                wins += 1

    if closed == 0:
        return 0.0
    return wins * 100.0 / closed


def summarize_result(result: BacktestResult) -> str:
    """백테스트 결과를 사람이 읽기 쉬운 텍스트로 요약합니다."""

    return "\n".join(
        [
            f"[{result.strategy_name}] {result.ticker}",
            f"- initial_capital: {result.initial_capital:,.0f} KRW",
            f"- final_equity: {result.final_equity:,.0f} KRW",
            f"- total_return: {result.total_return_pct:.2f}%",
            f"- max_drawdown: {result.max_drawdown_pct:.2f}%",
            f"- trade_count: {result.trade_count}",
            f"- win_rate: {result.win_rate_pct:.2f}%",
        ]
    )


def plot_results(results: list[BacktestResult], output_path: Path) -> None:
    """여러 전략의 자산곡선을 한 그래프에 저장합니다."""

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(13, 7))

    for result in results:
        ax.plot(
            result.equity_curve.index,
            result.equity_curve.values,
            linewidth=2.0,
            label=f"{result.strategy_name} ({result.total_return_pct:.1f}%)",
        )

    ax.set_title(f"V1 vs V2 Equity Curve - {results[0].ticker}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Time")
    ax.set_ylabel("Equity (KRW)")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)


def run_v1_backtest(
    ticker: str,
    day_df: pd.DataFrame,
    signal_df: pd.DataFrame,
    initial_capital: float,
    fee_rate: float,
    config: StrategyV1Config,
) -> BacktestResult:
    """V1 핵심 진입/청산 규칙을 단일 티커 기준으로 재생합니다."""

    cash = initial_capital
    quantity = 0.0
    avg_buy_price = 0.0
    trades: list[Trade] = []
    equity_points: list[tuple[pd.Timestamp, float]] = []

    for i in range(len(signal_df)):
        current_signal_df = signal_df.iloc[: i + 1]
        current_time = current_signal_df.index[-1]
        current_day_df = day_df[day_df.index <= current_time.normalize()]

        if len(current_day_df) == 0:
            continue

        close_price = float(current_signal_df["close"].iloc[-1])

        if quantity > 0:
            balances = build_balance_row(ticker, quantity, avg_buy_price)
            exit_signal = evaluate_v1_exit_signal(ticker, balances, current_signal_df, config)
            if exit_signal.should_sell:
                gross_value = quantity * close_price
                net_value = gross_value * (1.0 - fee_rate)
                cash += net_value
                trades.append(
                    Trade("sell", current_time, close_price, quantity, exit_signal.reason, cash)
                )
                quantity = 0.0
                avg_buy_price = 0.0

        if quantity == 0 and cash > 0:
            entry_signal = evaluate_v1_entry_signal(ticker, current_day_df, current_signal_df, config)
            order_budget = calculate_v1_order_budget(cash, config)
            if entry_signal.should_buy and order_budget > 0:
                budget = min(cash, order_budget)
                spend = budget * (1.0 - fee_rate)
                buy_quantity = spend / close_price if close_price else 0.0
                if buy_quantity > 0:
                    cash -= budget
                    quantity = buy_quantity
                    avg_buy_price = close_price
                    equity_after = cash + quantity * close_price
                    trades.append(
                        Trade("buy", current_time, close_price, quantity, entry_signal.reason, equity_after)
                    )

        equity = cash + quantity * close_price
        equity_points.append((current_time, equity))

    if quantity > 0 and len(signal_df) > 0:
        final_time = signal_df.index[-1]
        final_price = float(signal_df["close"].iloc[-1])
        gross_value = quantity * final_price
        net_value = gross_value * (1.0 - fee_rate)
        cash += net_value
        trades.append(Trade("sell", final_time, final_price, quantity, "end_of_backtest", cash))
        quantity = 0.0
        equity_points[-1] = (final_time, cash)

    equity_curve = pd.Series(
        [equity for _, equity in equity_points],
        index=[timestamp for timestamp, _ in equity_points],
        name="equity",
    )
    final_equity = float(equity_curve.iloc[-1]) if not equity_curve.empty else initial_capital
    total_return_pct = (final_equity / initial_capital - 1.0) * 100.0

    return BacktestResult(
        strategy_name="V1",
        ticker=ticker,
        initial_capital=initial_capital,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        max_drawdown_pct=compute_max_drawdown_pct(equity_curve),
        trade_count=len([trade for trade in trades if trade.side == "sell"]),
        win_rate_pct=compute_win_rate_pct(trades),
        trades=trades,
        equity_curve=equity_curve,
    )


def run_v2_backtest(
    ticker: str,
    day_df: pd.DataFrame,
    signal_df: pd.DataFrame,
    initial_capital: float,
    fee_rate: float,
    config: StrategyV2Config,
) -> BacktestResult:
    """V2 핵심 진입/청산 규칙을 단일 티커 기준으로 재생합니다."""

    cash = initial_capital
    quantity = 0.0
    avg_buy_price = 0.0
    trades: list[Trade] = []
    equity_points: list[tuple[pd.Timestamp, float]] = []

    for i in range(len(signal_df)):
        current_signal_df = signal_df.iloc[: i + 1]
        current_time = current_signal_df.index[-1]
        current_day_df = day_df[day_df.index <= current_time.normalize()]

        if len(current_day_df) == 0:
            continue

        close_price = float(current_signal_df["close"].iloc[-1])

        if quantity > 0:
            balances = build_balance_row(ticker, quantity, avg_buy_price)
            exit_signal = evaluate_v2_exit_signal(ticker, balances, current_signal_df, config)
            if exit_signal.should_sell:
                gross_value = quantity * close_price
                net_value = gross_value * (1.0 - fee_rate)
                cash += net_value
                trades.append(
                    Trade("sell", current_time, close_price, quantity, exit_signal.reason, cash)
                )
                quantity = 0.0
                avg_buy_price = 0.0

        if quantity == 0 and cash > 0:
            entry_signal = evaluate_v2_entry_signal(ticker, current_day_df, current_signal_df, config)
            order_budget = calculate_v2_order_budget(cash, current_signal_df, config)
            if entry_signal.should_buy and order_budget > 0:
                budget = min(cash, order_budget)
                spend = budget * (1.0 - fee_rate)
                buy_quantity = spend / close_price if close_price else 0.0
                if buy_quantity > 0:
                    cash -= budget
                    quantity = buy_quantity
                    avg_buy_price = close_price
                    equity_after = cash + quantity * close_price
                    trades.append(
                        Trade("buy", current_time, close_price, quantity, entry_signal.reason, equity_after)
                    )

        equity = cash + quantity * close_price
        equity_points.append((current_time, equity))

    if quantity > 0 and len(signal_df) > 0:
        final_time = signal_df.index[-1]
        final_price = float(signal_df["close"].iloc[-1])
        gross_value = quantity * final_price
        net_value = gross_value * (1.0 - fee_rate)
        cash += net_value
        trades.append(Trade("sell", final_time, final_price, quantity, "end_of_backtest", cash))
        quantity = 0.0
        equity_points[-1] = (final_time, cash)

    equity_curve = pd.Series(
        [equity for _, equity in equity_points],
        index=[timestamp for timestamp, _ in equity_points],
        name="equity",
    )
    final_equity = float(equity_curve.iloc[-1]) if not equity_curve.empty else initial_capital
    total_return_pct = (final_equity / initial_capital - 1.0) * 100.0

    return BacktestResult(
        strategy_name="V2",
        ticker=ticker,
        initial_capital=initial_capital,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        max_drawdown_pct=compute_max_drawdown_pct(equity_curve),
        trade_count=len([trade for trade in trades if trade.side == "sell"]),
        win_rate_pct=compute_win_rate_pct(trades),
        trades=trades,
        equity_curve=equity_curve,
    )


def validate_data(day_df: pd.DataFrame, signal_df: pd.DataFrame) -> None:
    """백테스트에 필요한 기본 컬럼과 데이터 길이를 검증합니다."""

    required_signal_columns = {"open", "high", "low", "close", "volume"}
    required_day_columns = {"close"}

    if day_df is None or signal_df is None or day_df.empty or signal_df.empty:
        raise ValueError("OHLCV data is empty. Check ticker/interval/count settings.")
    if not required_day_columns.issubset(day_df.columns):
        raise ValueError(f"Day dataframe must contain {sorted(required_day_columns)}")
    if not required_signal_columns.issubset(signal_df.columns):
        raise ValueError(f"Signal dataframe must contain {sorted(required_signal_columns)}")


def run_backtests(
    ticker: str,
    day_count: int,
    signal_count: int,
    initial_capital: float,
    fee_rate: float,
) -> list[BacktestResult]:
    """백테스트용 데이터를 불러오고 V1/V2 결과를 함께 반환합니다."""

    day_df = get_ohlcv(ticker, interval="day", count=day_count).copy()
    signal_df = get_ohlcv(ticker, interval="minute240", count=signal_count).copy()
    validate_data(day_df, signal_df)

    if not isinstance(day_df.index, pd.DatetimeIndex) or not isinstance(signal_df.index, pd.DatetimeIndex):
        raise ValueError("Expected DatetimeIndex from pyupbit OHLCV data.")

    v1_result = run_v1_backtest(
        ticker=ticker,
        day_df=day_df,
        signal_df=signal_df,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        config=StrategyV1Config(signal_interval="minute240", signal_count=signal_count),
    )
    v2_result = run_v2_backtest(
        ticker=ticker,
        day_df=day_df,
        signal_df=signal_df,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        config=StrategyV2Config(signal_count=signal_count),
    )
    return [v1_result, v2_result]


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱합니다."""

    parser = argparse.ArgumentParser(description="Compare V1 and V2 strategy backtests.")
    parser.add_argument("--ticker", default="KRW-BTC")
    parser.add_argument("--day-count", type=int, default=180)
    parser.add_argument("--signal-count", type=int, default=360)
    parser.add_argument("--initial-capital", type=float, default=1_000_000)
    parser.add_argument("--fee-rate", type=float, default=0.0005)
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "v1_v2_backtest.png"),
    )
    return parser.parse_args()


def main() -> None:
    """CLI 엔트리포인트입니다."""

    args = parse_args()
    results = run_backtests(
        ticker=args.ticker,
        day_count=args.day_count,
        signal_count=args.signal_count,
        initial_capital=args.initial_capital,
        fee_rate=args.fee_rate,
    )

    for result in results:
        print(summarize_result(result))

    output_path = Path(args.output)
    plot_results(results, output_path)
    print(f"saved_chart: {output_path}")


if __name__ == "__main__":
    main()
