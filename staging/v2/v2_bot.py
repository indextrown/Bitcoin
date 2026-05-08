from __future__ import annotations

"""V2 전략 실전 실행 스크립트.

기본값은 dry-run이며, ``--live`` 플래그를 줬을 때만 실제 주문을 전송합니다.
"""

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import argparse
import json
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.upbit_develop_library import (  # noqa: E402
    build_balance_map,
    buy_coin_market,
    create_upbit_client,
    get_ohlcv,
    get_total_money,
    get_total_real_money,
    sell_coin_market,
)
from operate.v2.strategy_v2 import (  # noqa: E402
    StrategyConfig,
    build_v2_signals,
    calculate_order_budget,
)


BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "v2_trade_log.jsonl"


def get_krw_balance(balances: list[dict[str, str]]) -> float:
    """잔고 목록에서 사용 가능한 KRW 잔고를 반환합니다."""

    for balance in balances:
        if balance.get("currency") == "KRW":
            return float(balance.get("balance", 0))
    return 0.0


def get_coin_volume(balance_map: dict[str, dict[str, str]], ticker: str) -> float:
    """특정 티커의 보유 수량과 잠긴 수량 합계를 반환합니다."""

    value = balance_map.get(ticker)
    if value is None:
        return 0.0
    return float(value.get("balance", 0)) + float(value.get("locked", 0))


def write_log(event_type: str, payload: dict[str, object]) -> None:
    """JSON Lines 형식으로 실행 로그를 저장합니다."""

    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event_type": event_type,
        "payload": payload,
    }
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=True) + "\n")


def format_account_summary(balances: list[dict[str, str]]) -> str:
    """현재 계좌 상태를 간단히 문자열로 요약합니다."""

    total_money = get_total_money(balances)
    total_real_money = get_total_real_money(balances)
    revenue_pct = 0.0
    if total_money > 0:
        revenue_pct = (total_real_money - total_money) * 100.0 / total_money

    return "\n".join(
        [
            "[Account Summary]",
            f"- total_money: {total_money:,.0f} KRW",
            f"- total_real_money: {total_real_money:,.0f} KRW",
            f"- total_revenue: {revenue_pct:.2f}%",
        ]
    )


def execute_sell_orders(
    upbit,
    balance_map: dict[str, dict[str, str]],
    sell_signals,
    live: bool,
) -> list[str]:
    """매도 신호에 따라 주문을 실행하거나 dry-run 메시지를 만듭니다."""

    messages: list[str] = []

    for signal in sell_signals:
        if not signal.should_sell:
            continue

        volume = get_coin_volume(balance_map, signal.ticker)
        if volume <= 0:
            messages.append(f"SELL SKIP {signal.ticker}: no_volume")
            continue

        message = (
            f"SELL {signal.ticker}: reason={signal.reason}, revenue={signal.revenue_rate:.2f}%, "
            f"close={signal.close_price:.0f}, volume={volume:.8f}"
        )
        messages.append(message)
        write_log("sell_signal", {"ticker": signal.ticker, "signal": asdict(signal), "volume": volume})

        if live:
            sell_result = sell_coin_market(upbit, signal.ticker, volume, wait_seconds=1.0)
            write_log("sell_executed", {"ticker": signal.ticker, "balances": sell_result})

    return messages


def execute_buy_orders(
    upbit,
    balances: list[dict[str, str]],
    buy_signals,
    config: StrategyConfig,
    live: bool,
) -> list[str]:
    """매수 후보에 따라 주문을 실행하거나 dry-run 메시지를 만듭니다."""

    messages: list[str] = []
    working_balances = balances

    sorted_signals = sorted(
        [signal for signal in buy_signals if signal.should_buy],
        key=lambda signal: (signal.volume_ratio, signal.rsi_now),
        reverse=True,
    )

    for signal in sorted_signals:
        krw_balance = get_krw_balance(working_balances)
        signal_df = None
        order_budget = 0.0

        # 실제 주문 직전의 예산은 최신 KRW 잔고 기준으로 다시 계산합니다.
        try:
            signal_df = get_ohlcv(signal.ticker, interval=config.signal_interval, count=config.signal_count)
            order_budget = calculate_order_budget(krw_balance, signal_df, config)
        except Exception:
            order_budget = 0.0

        if order_budget <= 0:
            messages.append(f"BUY SKIP {signal.ticker}: insufficient_budget")
            continue

        message = (
            f"BUY {signal.ticker}: reason={signal.reason}, budget={order_budget:,.0f} KRW, "
            f"close={signal.close_price:.0f}, breakout={signal.breakout_level:.0f}, "
            f"volume_ratio={signal.volume_ratio:.2f}, rsi={signal.rsi_now:.2f}"
        )
        messages.append(message)
        write_log("buy_signal", {"ticker": signal.ticker, "signal": asdict(signal), "order_budget": order_budget})

        if live:
            working_balances = buy_coin_market(upbit, signal.ticker, order_budget, wait_seconds=1.0)
            write_log("buy_executed", {"ticker": signal.ticker, "balances": working_balances})
        else:
            krw_after = max(0.0, krw_balance - order_budget)
            simulated_balances = []
            for balance in working_balances:
                if balance.get("currency") == "KRW":
                    updated = dict(balance)
                    updated["balance"] = f"{krw_after}"
                    simulated_balances.append(updated)
                else:
                    simulated_balances.append(balance)
            working_balances = simulated_balances

    return messages


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱합니다."""

    parser = argparse.ArgumentParser(description="Run the V2 strategy bot.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--market", default="KRW")
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--max-holdings", type=int, default=4)
    parser.add_argument("--allocation-ratio", type=float, default=0.2)
    parser.add_argument("--risk-per-trade-ratio", type=float, default=0.02)
    parser.add_argument("--live", action="store_true", help="Place real orders instead of dry-run.")
    return parser.parse_args()


def main() -> None:
    """V2 전략 스캔, 요약, 선택적 실주문을 수행합니다."""

    args = parse_args()
    config = StrategyConfig(
        market=args.market,
        top_n=args.top_n,
        max_holdings=args.max_holdings,
        allocation_ratio=args.allocation_ratio,
        risk_per_trade_ratio=args.risk_per_trade_ratio,
    )

    upbit = create_upbit_client(env_file=args.env_file)
    balances = upbit.get_balances()
    krw_balance = get_krw_balance(balances)
    balance_map = build_balance_map(balances)
    result = build_v2_signals(balances, krw_balance=krw_balance, config=config)

    print(f"[V2 Bot] mode={'LIVE' if args.live else 'DRY_RUN'}")
    print(format_account_summary(balances))
    print(f"- top_tickers: {', '.join(result['top_tickers']) if result['top_tickers'] else '(none)'}")
    print(f"- buy_candidates: {len(result['buy_signals'])}")
    print(f"- sell_candidates: {len(result['sell_signals'])}")

    sell_messages = execute_sell_orders(upbit, balance_map, result["sell_signals"], args.live)
    buy_messages = execute_buy_orders(upbit, balances, result["buy_signals"], config, args.live)

    if not sell_messages and not buy_messages:
        print("- action: no_orders")
    else:
        for message in sell_messages + buy_messages:
            print(f"- action: {message}")


if __name__ == "__main__":
    main()
