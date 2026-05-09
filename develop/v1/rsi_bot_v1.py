from __future__ import annotations

# ==========================
# V1 RSI 실사용 봇 알고리즘
# ==========================
# 대상 코인 선정
# 최근 거래대금 상위 top 10 코인만 봅니다.
# 동시에 보유할 수 있는 코인은 최대 5개입니다.
#
# 기준 지표
# 60분봉 RSI(14)를 사용합니다.
# 봇은 15분마다 실행하는 것을 기준으로 설계합니다.
#
# 신규 진입
# 이전 RSI <= 30 이고 현재 RSI > 30 이면 과매도 이탈로 봅니다.
# 아직 해당 코인을 보유하지 않았고, 전체 보유 코인 수가 5개 미만이면 첫 진입합니다.
# 첫 진입 금액은 코인당 최대 투자금의 10%입니다.
#
# 보유 코인 추가 매수
# 이미 보유 중인 코인도 같은 RSI 반등 신호를 사용합니다.
# 현재 투자 비중이 코인당 최대 투자금의 50% 이하면 일반 물타기합니다.
# 50%를 초과한 상태에서는 수익률이 -5% 이하일 때만 추가 물타기합니다.
# 추가 매수 금액은 코인당 최대 투자금의 5%입니다.
#
# 익절 매도
# RSI >= 70 이고 수익률 >= 1%이면 익절 조건을 확인합니다.
# 현재 매수금액이 코인당 최대 투자금의 25% 미만이면 전량 매도합니다.
# 25% 이상이면 절반 매도합니다.
#
# 손절 매도
# 남은 원화가 추가 매수 금액보다 적고, 수익률이 -10% 이하이면 절반 손절합니다.

import os
import textwrap
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from typing import Any

from develop.upbit_develop_library import (
    buy_coin_market,
    cancel_coin_orders,
    create_upbit_client,
    get_coin_now_money,
    get_has_coin_count,
    get_ohlcv,
    get_revenue_rate,
    get_rsi,
    get_top_coin_list,
    get_total_real_money,
    has_coin,
    sell_coin_market,
)


DRY_RUN = True
MIN_TRADE_KRW = 5000.0
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "indextrown@gmail.com")
TO_EMAIL = [email for email in os.getenv("TO_EMAILS", GMAIL_ADDRESS).split(",") if email]
GMAIL_APP_PASSWORD = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")


@dataclass(frozen=True)
class StrategyConfig:
    """RSI 다중 코인 반등 전략의 기준값입니다."""

    market: str = "KRW"
    top_n: int = 10
    top_interval: str = "day"
    signal_interval: str = "minute60"
    signal_count: int = 80
    rsi_period: int = 14
    rsi_entry_threshold: float = 30.0
    rsi_exit_threshold: float = 70.0
    max_coin_count: int = 5
    first_rate_pct: float = 10.0
    water_rate_pct: float = 5.0
    water_limit_pct: float = 50.0
    water2_min_loss_pct: float = -5.0
    take_profit_min_pct: float = 1.0
    full_sell_below_alloc_pct: float = 25.0
    loss_cut_pct: float = -10.0
    sleep_seconds: float = 0.0


@dataclass(frozen=True)
class SignalSnapshot:
    """코인별 RSI 전략 판단에 필요한 현재 상태입니다."""

    ticker: str
    price: float
    rsi_prev: float
    rsi_now: float
    revenue_rate: float
    invested_krw: float
    allocation_pct: float
    holding: bool


@dataclass(frozen=True)
class TradePlan:
    """현재 캔들에서 제안하는 주문 계획입니다."""

    ticker: str
    action: str
    reason: str
    order_budget_krw: float
    sell_ratio: float
    snapshot: SignalSnapshot


CONFIG = StrategyConfig(
    market="KRW",
    top_n=10,
    top_interval="day",
    signal_interval="minute60",
    signal_count=80,
    rsi_period=14,
    rsi_entry_threshold=30.0,
    rsi_exit_threshold=70.0,
    max_coin_count=5,
    first_rate_pct=10.0,
    water_rate_pct=5.0,
    water_limit_pct=50.0,
    water2_min_loss_pct=-5.0,
    take_profit_min_pct=1.0,
    full_sell_below_alloc_pct=25.0,
    loss_cut_pct=-10.0,
    sleep_seconds=0.05,
)


def calculate_coin_max_money(
    total_seed_krw: float,
    config: StrategyConfig = StrategyConfig(),
) -> float:
    return total_seed_krw / config.max_coin_count


def calculate_first_enter_money(
    total_seed_krw: float,
    config: StrategyConfig = StrategyConfig(),
) -> float:
    return calculate_coin_max_money(total_seed_krw, config) * (config.first_rate_pct / 100)


def calculate_water_enter_money(
    total_seed_krw: float,
    config: StrategyConfig = StrategyConfig(),
) -> float:
    return calculate_coin_max_money(total_seed_krw, config) * (config.water_rate_pct / 100)


def build_snapshot(
    ticker: str,
    balances: list[dict[str, Any]],
    total_seed_krw: float,
    config: StrategyConfig = StrategyConfig(),
) -> SignalSnapshot:
    df = get_ohlcv(ticker, interval=config.signal_interval, count=config.signal_count)
    invested_krw = get_coin_now_money(balances, ticker)
    coin_max_money = calculate_coin_max_money(total_seed_krw, config)
    allocation_pct = (invested_krw / coin_max_money * 100) if coin_max_money > 0 else 0.0
    holding = has_coin(balances, ticker)
    revenue_rate = get_revenue_rate(balances, ticker, sleep_seconds=config.sleep_seconds) if holding else 0.0
    return SignalSnapshot(
        ticker=ticker,
        price=float(df["close"].iloc[-1]),
        rsi_prev=get_rsi(df, config.rsi_period, -3),
        rsi_now=get_rsi(df, config.rsi_period, -2),
        revenue_rate=revenue_rate,
        invested_krw=invested_krw,
        allocation_pct=allocation_pct,
        holding=holding,
    )


def is_rsi_rebound(snapshot: SignalSnapshot, config: StrategyConfig = StrategyConfig()) -> bool:
    return snapshot.rsi_prev <= config.rsi_entry_threshold and snapshot.rsi_now > config.rsi_entry_threshold


def evaluate_new_entry(
    snapshot: SignalSnapshot,
    holding_count: int,
    available_krw: float,
    total_seed_krw: float,
    config: StrategyConfig = StrategyConfig(),
) -> TradePlan:
    first_enter_money = calculate_first_enter_money(total_seed_krw, config)
    if snapshot.holding:
        return TradePlan(snapshot.ticker, "WAIT", "already_holding", 0.0, 0.0, snapshot)
    if holding_count >= config.max_coin_count:
        return TradePlan(snapshot.ticker, "WAIT", "max_coin_count_reached", 0.0, 0.0, snapshot)
    if not is_rsi_rebound(snapshot, config):
        return TradePlan(snapshot.ticker, "WAIT", "no_rsi_rebound", 0.0, 0.0, snapshot)
    order_budget = min(first_enter_money, available_krw)
    if order_budget <= 0:
        return TradePlan(snapshot.ticker, "WAIT", "insufficient_krw", 0.0, 0.0, snapshot)
    return TradePlan(snapshot.ticker, "BUY-NEW", "rsi_rebound_new_entry", order_budget, 0.0, snapshot)


def evaluate_holding_plan(
    snapshot: SignalSnapshot,
    available_krw: float,
    total_seed_krw: float,
    config: StrategyConfig = StrategyConfig(),
) -> TradePlan:
    water_enter_money = calculate_water_enter_money(total_seed_krw, config)
    coin_max_money = calculate_coin_max_money(total_seed_krw, config)

    if not snapshot.holding:
        return TradePlan(snapshot.ticker, "WAIT", "not_holding", 0.0, 0.0, snapshot)

    if snapshot.rsi_now >= config.rsi_exit_threshold and snapshot.revenue_rate >= config.take_profit_min_pct:
        if snapshot.invested_krw < coin_max_money * (config.full_sell_below_alloc_pct / 100):
            return TradePlan(snapshot.ticker, "SELL-PROFIT-ALL", "take_profit_full", 0.0, 1.0, snapshot)
        return TradePlan(snapshot.ticker, "SELL-PROFIT-HALF", "take_profit_half", 0.0, 0.5, snapshot)

    if available_krw < water_enter_money and snapshot.revenue_rate <= config.loss_cut_pct:
        return TradePlan(snapshot.ticker, "SELL-LOSS-HALF", "krw_shortage_loss_cut", 0.0, 0.5, snapshot)

    if not is_rsi_rebound(snapshot, config):
        return TradePlan(snapshot.ticker, "WAIT", "no_rsi_rebound", 0.0, 0.0, snapshot)

    if snapshot.allocation_pct <= config.water_limit_pct:
        order_budget = min(water_enter_money, available_krw)
        if order_budget <= 0:
            return TradePlan(snapshot.ticker, "WAIT", "insufficient_krw", 0.0, 0.0, snapshot)
        return TradePlan(snapshot.ticker, "BUY-WATER-1", "water_under_50pct", order_budget, 0.0, snapshot)

    if snapshot.revenue_rate <= config.water2_min_loss_pct:
        order_budget = min(water_enter_money, available_krw)
        if order_budget <= 0:
            return TradePlan(snapshot.ticker, "WAIT", "insufficient_krw", 0.0, 0.0, snapshot)
        return TradePlan(snapshot.ticker, "BUY-WATER-2", "water_over_50pct_and_loss", order_budget, 0.0, snapshot)

    return TradePlan(snapshot.ticker, "WAIT", "over_50pct_without_loss_condition", 0.0, 0.0, snapshot)


def build_rsi_trade_plans(
    balances: list[dict[str, Any]],
    available_krw: float,
    total_seed_krw: float,
    config: StrategyConfig = StrategyConfig(),
) -> list[TradePlan]:
    top_tickers = get_top_coin_list(
        interval=config.top_interval,
        top=config.top_n,
        market=config.market,
        sleep_seconds=config.sleep_seconds,
    )
    holding_count = get_has_coin_count(balances)
    plans: list[TradePlan] = []
    for ticker in top_tickers:
        snapshot = build_snapshot(ticker, balances, total_seed_krw, config)
        if snapshot.holding:
            plan = evaluate_holding_plan(snapshot, available_krw, total_seed_krw, config)
        else:
            plan = evaluate_new_entry(snapshot, holding_count, available_krw, total_seed_krw, config)
        plans.append(plan)
    return plans


def send_gmail(subject: str, body: str) -> None:
    """설정이 있으면 Gmail로 실행 결과를 보냅니다."""

    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD and TO_EMAIL):
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = ", ".join(TO_EMAIL)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as exc:
        print(f"메일 전송 실패: {exc}")


def format_plan_message(plan: TradePlan, label: str) -> str:
    """주문 결과를 사람이 읽기 쉽게 정리합니다."""

    snapshot = plan.snapshot
    return textwrap.dedent(
        f"""\
        [{label}]
        - ticker: {plan.ticker}
        - action: {plan.action}
        - reason: {plan.reason}
        - price: {snapshot.price:,.0f} KRW
        - RSI: {snapshot.rsi_prev:.2f} -> {snapshot.rsi_now:.2f}
        - revenue: {snapshot.revenue_rate:.2f}%
        - allocation: {snapshot.allocation_pct:.2f}%
        - budget: {plan.order_budget_krw:,.0f} KRW
        - sell_ratio: {plan.sell_ratio:.2f}
        - time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
    )


def execute_plan(upbit, plan: TradePlan) -> None:
    """매수/매도 계획을 실제 주문으로 실행합니다."""

    if plan.action == "WAIT":
        print(format_plan_message(plan, "WAIT"))
        return

    if DRY_RUN:
        msg = format_plan_message(plan, "DRY RUN")
        print(msg)
        send_gmail("[DRY RUN] V1 RSI Bot", msg)
        return

    if plan.action.startswith("BUY"):
        if plan.order_budget_krw < MIN_TRADE_KRW:
            print(format_plan_message(plan, "SKIP: BELOW_MIN_TRADE"))
            return
        cancel_coin_orders(upbit, plan.ticker, sleep_seconds=0.05)
        buy_coin_market(upbit, plan.ticker, plan.order_budget_krw, wait_seconds=1.5)
        msg = format_plan_message(plan, "BUY EXECUTED")
        print(msg)
        send_gmail("[BUY EXECUTED] V1 RSI Bot", msg)
        return

    if plan.action.startswith("SELL"):
        cancel_coin_orders(upbit, plan.ticker, sleep_seconds=0.05)
        balance_volume = float(upbit.get_balance(plan.ticker))
        sell_volume = balance_volume * plan.sell_ratio
        if sell_volume <= 0:
            print(format_plan_message(plan, "SKIP: NO_VOLUME"))
            return
        sell_coin_market(upbit, plan.ticker, sell_volume, wait_seconds=1.5)
        msg = format_plan_message(plan, "SELL EXECUTED")
        print(msg)
        send_gmail("[SELL EXECUTED] V1 RSI Bot", msg)


def main() -> None:
    """RSI 전략 실사용 봇 1회 실행 진입점입니다."""

    upbit = create_upbit_client()
    balances = upbit.get_balances()
    total_seed_krw = get_total_real_money(balances)
    available_krw = float(upbit.get_balance("KRW"))

    plans = build_rsi_trade_plans(
        balances=balances,
        available_krw=available_krw,
        total_seed_krw=total_seed_krw,
        config=CONFIG,
    )

    print(
        f"[V1 RSI Bot] dry_run={DRY_RUN} "
        f"holding={get_has_coin_count(balances)} "
        f"seed={total_seed_krw:,.0f} KRW"
    )

    for plan in plans:
        execute_plan(upbit, plan)


if __name__ == "__main__":
    main()
