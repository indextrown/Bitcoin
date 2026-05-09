from __future__ import annotations

# ==========================
# V1 단타 실사용 봇 알고리즘
# ==========================
# 대상 코인 선정
# 최근 거래대금 상위 top 10 코인만 봅니다.
# 동시에 보유할 수 있는 코인은 최대 5개입니다.
#
# 기준 지표
# 15분봉 MA5, MA20을 사용합니다.
# MA5가 MA20 아래에 있으면서, 짧은 하락 후 상승 반전이 나오면 매수 후보로 봅니다.
#
# 신규 진입
# MA5 < MA20 이고, ma5_before3 > ma5_before2 < ma5 이면 반등 시작으로 판단합니다.
# 아직 해당 코인을 보유하지 않았고, 전체 보유 코인 수가 5개 미만이면 첫 진입합니다.
# 첫 진입 금액은 코인당 최대 투자금의 10%입니다.
#
# 익절 방식
# 시장가 매수 후 평균 단가 대비 +1% 가격에 지정가 매도를 걸어 둡니다.
# 이미 보유 중인 코인은 현재가가 목표가 이상이면 시장가 매도로 정리합니다.
#
# 전략 성격
# 15분봉 단타용으로, 빠른 반등 구간을 짧게 먹고 나오는 구조입니다.
# 물타기 없이 단순 진입/익절 위주로 동작합니다.

import os
import textwrap
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import time
from typing import Any

from develop.upbit_develop_library import (
    buy_coin_market,
    cancel_coin_orders,
    create_upbit_client,
    get_avg_buy_price,
    get_current_price,
    get_has_coin_count,
    get_moving_average,
    get_ohlcv,
    get_top_coin_list,
    get_total_real_money,
    has_coin,
    sell_coin_market,
    sell_coin_limit,
)


DRY_RUN = True
MIN_TRADE_KRW = 5000.0
REQUEST_SLEEP_SECONDS = 0.2
USE_TOP_TICKERS = True
TOP_N = 10
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "indextrown@gmail.com")
TO_EMAIL = [email for email in os.getenv("TO_EMAILS", GMAIL_ADDRESS).split(",") if email]
GMAIL_APP_PASSWORD = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")


@dataclass(frozen=True)
class StrategyConfig:
    """15분봉 단타 전략의 기준값입니다."""

    ticker: str = "KRW-BTC"
    market: str = "KRW"
    signal_interval: str = "minute15"
    signal_count: int = 80
    short_ma_period: int = 5
    long_ma_period: int = 20
    max_coin_count: int = 5
    first_rate_pct: float = 10.0
    target_profit_pct: float = 1.0


@dataclass(frozen=True)
class SignalSnapshot:
    """단타 전략 판단에 필요한 현재 상태입니다."""

    ticker: str
    price: float
    ma5_before3: float
    ma5_before2: float
    ma5_now: float
    ma20_now: float
    avg_buy_price: float
    holding: bool


@dataclass(frozen=True)
class TradePlan:
    """현재 캔들에서 제안하는 단타 주문 계획입니다."""

    ticker: str
    action: str
    reason: str
    order_budget_krw: float
    target_price: float
    snapshot: SignalSnapshot


CONFIG = StrategyConfig(
    ticker="KRW-BTC",
    market="KRW",
    signal_interval="minute15",
    signal_count=80,
    short_ma_period=5,
    long_ma_period=20,
    max_coin_count=5,
    first_rate_pct=10.0,
    target_profit_pct=1.0,
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


def build_snapshot(
    ticker: str,
    balances: list[dict[str, Any]],
    config: StrategyConfig = StrategyConfig(),
) -> SignalSnapshot:
    df = get_ohlcv(ticker, interval=config.signal_interval, count=config.signal_count)
    return SignalSnapshot(
        ticker=ticker,
        price=float(df["close"].iloc[-1]),
        ma5_before3=get_moving_average(df, config.short_ma_period, -4),
        ma5_before2=get_moving_average(df, config.short_ma_period, -3),
        ma5_now=get_moving_average(df, config.short_ma_period, -2),
        ma20_now=get_moving_average(df, config.long_ma_period, -2),
        avg_buy_price=get_avg_buy_price(balances, ticker),
        holding=has_coin(balances, ticker),
    )


def is_scalp_rebound(snapshot: SignalSnapshot) -> bool:
    return (
        snapshot.ma5_now < snapshot.ma20_now
        and snapshot.ma5_before3 > snapshot.ma5_before2
        and snapshot.ma5_before2 < snapshot.ma5_now
    )


def evaluate_entry_signal(
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
    if not is_scalp_rebound(snapshot):
        return TradePlan(snapshot.ticker, "WAIT", "no_scalp_rebound", 0.0, 0.0, snapshot)
    order_budget = min(first_enter_money, available_krw)
    if order_budget <= 0:
        return TradePlan(snapshot.ticker, "WAIT", "insufficient_krw", 0.0, 0.0, snapshot)
    target_price = snapshot.price * (1 + config.target_profit_pct / 100)
    return TradePlan(snapshot.ticker, "BUY-NEW2-15M", "ma_rebound_entry", order_budget, target_price, snapshot)


def evaluate_exit_signal(
    snapshot: SignalSnapshot,
    config: StrategyConfig = StrategyConfig(),
) -> TradePlan:
    if not snapshot.holding:
        return TradePlan(snapshot.ticker, "WAIT", "not_holding", 0.0, 0.0, snapshot)
    if snapshot.avg_buy_price <= 0:
        return TradePlan(snapshot.ticker, "WAIT", "missing_avg_buy_price", 0.0, 0.0, snapshot)
    target_price = snapshot.avg_buy_price * (1 + config.target_profit_pct / 100)
    if snapshot.price >= target_price:
        return TradePlan(snapshot.ticker, "SELL-TARGET-1PCT", "target_profit_hit", 0.0, 1.0, snapshot)
    return TradePlan(snapshot.ticker, "WAIT", "target_not_reached", 0.0, target_price, snapshot)


def build_scalp_signal(
    balances: list[dict[str, Any]],
    available_krw: float,
    total_seed_krw: float,
    config: StrategyConfig = StrategyConfig(),
) -> dict[str, Any]:
    snapshot = build_snapshot(config.ticker, balances, config)
    holding_count = get_has_coin_count(balances)
    entry_signal = evaluate_entry_signal(snapshot, holding_count, available_krw, total_seed_krw, config)
    exit_signal = evaluate_exit_signal(snapshot, config) if snapshot.holding else None
    return {
        "config": config,
        "snapshot": snapshot,
        "entry_signal": entry_signal,
        "exit_signal": exit_signal,
    }


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
        - MA5: {snapshot.ma5_before3:.2f} -> {snapshot.ma5_before2:.2f} -> {snapshot.ma5_now:.2f}
        - MA20: {snapshot.ma20_now:.2f}
        - budget: {plan.order_budget_krw:,.0f} KRW
        - target_price: {plan.target_price:,.2f}
        - time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
    )


def execute_entry(upbit, plan: TradePlan) -> None:
    """단타 신규 진입을 실행하고 익절 지정가를 겁니다."""

    if plan.order_budget_krw < MIN_TRADE_KRW:
        print(format_plan_message(plan, "SKIP: BELOW_MIN_TRADE"))
        return

    if DRY_RUN:
        msg = format_plan_message(plan, "DRY RUN ENTRY")
        print(msg)
        send_gmail("[DRY RUN] V1 Scalp Entry", msg)
        return

    cancel_coin_orders(upbit, plan.ticker, sleep_seconds=0.05)
    balances = buy_coin_market(upbit, plan.ticker, plan.order_budget_krw, wait_seconds=1.5)
    avg_price = get_avg_buy_price(balances, plan.ticker)
    volume = float(upbit.get_balance(plan.ticker))
    target_price = avg_price * (1 + CONFIG.target_profit_pct / 100)
    if volume > 0:
        sell_coin_limit(upbit, plan.ticker, target_price, volume)

    msg = format_plan_message(
        TradePlan(plan.ticker, plan.action, plan.reason, plan.order_budget_krw, target_price, plan.snapshot),
        "BUY EXECUTED",
    )
    print(msg)
    send_gmail("[BUY EXECUTED] V1 Scalp Bot", msg)


def execute_exit(upbit, plan: TradePlan) -> None:
    """단타 목표가 도달 시 시장가 매도를 실행합니다."""

    if DRY_RUN:
        msg = format_plan_message(plan, "DRY RUN EXIT")
        print(msg)
        send_gmail("[DRY RUN] V1 Scalp Exit", msg)
        return

    cancel_coin_orders(upbit, plan.ticker, sleep_seconds=0.05)
    volume = float(upbit.get_balance(plan.ticker))
    if volume <= 0:
        print(format_plan_message(plan, "SKIP: NO_VOLUME"))
        return
    sell_coin_market(upbit, plan.ticker, volume, wait_seconds=1.5)
    msg = format_plan_message(plan, "SELL EXECUTED")
    print(msg)
    send_gmail("[SELL EXECUTED] V1 Scalp Bot", msg)


def target_price_now(ticker: str, balances: list[dict]) -> float:
    """현재 평균 단가 기준 익절 목표가를 계산합니다."""

    avg_price = get_avg_buy_price(balances, ticker)
    if avg_price <= 0:
        return 0.0
    return avg_price * (1 + CONFIG.target_profit_pct / 100)


def main() -> None:
    """단타 전략 실사용 봇 1회 실행 진입점입니다."""

    upbit = create_upbit_client()
    balances = upbit.get_balances()
    total_seed_krw = get_total_real_money(balances)
    available_krw = float(upbit.get_balance("KRW"))

    tickers = [CONFIG.ticker]
    if USE_TOP_TICKERS:
        tickers = get_top_coin_list("day", TOP_N, market=CONFIG.market, sleep_seconds=0.05)

    print(
        f"[V1 Scalp Bot] dry_run={DRY_RUN} "
        f"holding={get_has_coin_count(balances)} "
        f"seed={total_seed_krw:,.0f} KRW"
    )

    for ticker in tickers:
        time.sleep(REQUEST_SLEEP_SECONDS)

        runtime_config = StrategyConfig(
            ticker=ticker,
            market=CONFIG.market,
            signal_interval=CONFIG.signal_interval,
            signal_count=CONFIG.signal_count,
            short_ma_period=CONFIG.short_ma_period,
            long_ma_period=CONFIG.long_ma_period,
            max_coin_count=CONFIG.max_coin_count,
            first_rate_pct=CONFIG.first_rate_pct,
            target_profit_pct=CONFIG.target_profit_pct,
        )

        result = build_scalp_signal(
            balances=balances,
            available_krw=available_krw,
            total_seed_krw=total_seed_krw,
            config=runtime_config,
        )
        snapshot = result["snapshot"]
        entry_signal: TradePlan = result["entry_signal"]
        exit_signal: TradePlan | None = result["exit_signal"]

        if snapshot.holding and exit_signal is not None and exit_signal.action == "SELL-TARGET-1PCT":
            execute_exit(upbit, exit_signal)
            balances = upbit.get_balances()
            available_krw = float(upbit.get_balance("KRW"))
            continue

        if snapshot.holding:
            target_price = target_price_now(ticker, balances)
            current_price = get_current_price(ticker) or snapshot.price
            msg = textwrap.dedent(
                f"""\
                [HOLD]
                - ticker: {ticker}
                - current_price: {current_price:,.0f} KRW
                - target_price: {target_price:,.2f}
                - time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
            )
            print(msg)
            if not DRY_RUN:
                cancel_coin_orders(upbit, ticker, sleep_seconds=0.05)
                volume = float(upbit.get_balance(ticker))
                if volume > 0 and target_price > 0:
                    sell_coin_limit(upbit, ticker, target_price, volume)
            continue

        if entry_signal.action == "BUY-NEW2-15M":
            execute_entry(upbit, entry_signal)
            balances = upbit.get_balances()
            available_krw = float(upbit.get_balance("KRW"))
        else:
            print(format_plan_message(entry_signal, "WAIT"))


if __name__ == "__main__":
    main()
