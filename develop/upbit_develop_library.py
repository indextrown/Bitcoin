"""`develop` 폴더의 예제 스크립트에서 공통 유틸만 모아둔 라이브러리입니다.

여러 파일에 흩어져 있던 지표 계산, 잔고 조회, 주문 보조 함수를 한곳에
정리했습니다. 기존 매매 시나리오 전체를 옮기지는 않았고, 앞으로 다른
자동매매 코드나 분석 코드에서 재사용할 수 있는 함수만 남겨두었습니다.
"""

from __future__ import annotations

import os
import time
from typing import Any, Iterable

import pandas as pd
import pyupbit
from dotenv import load_dotenv

Balance = dict[str, Any]
BalanceMap = dict[str, Balance]

_TOP_COIN_LIST_CACHE: dict[tuple[str, int, str], tuple[float, list[str]]] = {}


def _compose_balance_ticker(balance: Balance) -> str:
    """업비트 잔고 한 줄 데이터를 ``KRW-BTC`` 형태 티커로 변환합니다."""

    unit_currency = balance.get("unit_currency", "KRW")
    currency = balance.get("currency", "")
    return f"{unit_currency}-{currency}"


def _chunked(items: list[str], chunk_size: int) -> list[list[str]]:
    """문자열 목록을 지정한 크기만큼 나눠 반환합니다."""

    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def build_balance_map(balances: Iterable[Balance]) -> BalanceMap:
    """잔고 목록을 ``{티커: 잔고행}`` 형태 딕셔너리로 변환합니다."""

    balance_map: BalanceMap = {}
    for value in balances:
        ticker = _compose_balance_ticker(value)
        balance_map[ticker] = value
    return balance_map


def _get_balance_map(balances: Iterable[Balance] | BalanceMap) -> BalanceMap:
    """잔고 입력이 목록이든 딕셔너리든 동일하게 딕셔너리 형태로 맞춥니다."""

    if isinstance(balances, dict):
        return balances
    return build_balance_map(balances)


def is_ticker_in_list(coin_list: Iterable[str], ticker: str) -> bool:
    """티커가 목록 안에 있으면 ``True``를 반환합니다.

    같은 목록으로 반복 검사할 때는 ``set``을 넘기면 더 빠르게 조회할 수 있습니다.
    """

    if isinstance(coin_list, (set, frozenset, list, tuple)):
        return ticker in coin_list
    return ticker in set(coin_list)


def calculate_rsi_series(
    ohlcv: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    """OHLCV 데이터에서 RSI 시리즈 전체를 계산합니다."""

    delta = ohlcv["close"].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=period - 1, min_periods=period).mean()
    ma_down = down.ewm(com=period - 1, min_periods=period).mean()
    rs = ma_up / ma_down
    return pd.Series(100 - (100 / (1 + rs)), name="RSI")


def get_rsi(
    ohlcv: pd.DataFrame,
    period: int = 14,
    st: int = -1,
) -> float:
    """원하는 위치의 RSI 값 하나를 반환합니다.

    Args:
        ohlcv: ``close`` 컬럼이 포함된 OHLCV 데이터프레임입니다.
        period: RSI 계산 기간입니다.
        st: 위치 인덱스입니다. ``-1``은 현재 캔들, ``-2``는 이전 캔들입니다.
    """

    return float(calculate_rsi_series(ohlcv, period).iloc[st])


def get_moving_average(
    ohlcv: pd.DataFrame,
    period: int,
    st: int = -1,
) -> float:
    """종가 기준 이동평균선 값을 반환합니다."""

    ma = ohlcv["close"].rolling(period).mean()
    return float(ma.iloc[st])


# ======================================================================
# 아래 함수들은 업비트에서 이미 받아온 잔고 데이터가 있어야 사용하는 구간입니다.
# 직접 API를 호출하지는 않지만, 업비트 응답 형식에 의존합니다.
# ======================================================================

def has_coin(balances: Iterable[Balance], ticker: str) -> bool:
    """잔고 목록에 해당 코인이 포함되어 있는지 확인합니다."""

    balance_map = _get_balance_map(balances)
    return ticker in balance_map


def get_coin_now_money(balances: Iterable[Balance], ticker: str) -> float:
    """특정 코인에 들어간 총 매수 금액을 반환합니다.

    지정가 매도 주문으로 묶여 있는 수량도 내 보유분이므로 ``locked``까지 함께
    포함해서 계산합니다.
    """

    balance_map = _get_balance_map(balances)
    value = balance_map.get(ticker)
    if value is not None:
        avg_buy_price = float(value.get("avg_buy_price", 0))
        balance = float(value.get("balance", 0))
        locked = float(value.get("locked", 0))
        return avg_buy_price * (balance + locked)

    return 0.0


def get_has_coin_count(balances: Iterable[Balance]) -> int:
    """보유 코인 개수를 반환합니다.

    원화와 평균매입단가가 0인 에어드랍 코인은 제외합니다.
    """

    count = 0
    for value in balances:
        if float(value.get("avg_buy_price", 0)) != 0:
            count += 1
    return count


def get_avg_buy_price(balances: Iterable[Balance], ticker: str) -> float:
    """특정 코인의 평균 매입 단가를 반환합니다."""

    balance_map = _get_balance_map(balances)
    value = balance_map.get(ticker)
    if value is None:
        return 0.0
    return float(value.get("avg_buy_price", 0))


def get_total_money(balances: Iterable[Balance]) -> float:
    """보유 원화와 각 코인의 평균매입단가 기준 총 원금을 반환합니다."""

    total = 0.0
    for value in balances:
        try:
            currency = value.get("currency")
            balance = float(value.get("balance", 0))
            locked = float(value.get("locked", 0))

            if currency == "KRW":
                total += balance + locked
                continue

            avg_buy_price = float(value.get("avg_buy_price", 0))
            if avg_buy_price != 0 and (balance != 0 or locked != 0):
                total += avg_buy_price * (balance + locked)
        except Exception:
            continue

    return total


# ======================================================================
# 아래 함수들은 업비트 API 호출 또는 인증 정보가 필요한 구간입니다.
# ======================================================================

def create_upbit_client(
    env_file: str = ".env",
    access_key_var: str = "ACCESS_KEY",
    secret_key_var: str = "SECRET_KEY",
) -> pyupbit.Upbit:
    """환경 변수에 저장된 키로 인증된 Upbit 클라이언트를 생성합니다.

    Args:
        env_file: 키를 읽기 전에 불러올 dotenv 파일 경로입니다.
        access_key_var: 액세스 키가 들어있는 환경 변수 이름입니다.
        secret_key_var: 시크릿 키가 들어있는 환경 변수 이름입니다.

    Returns:
        인증이 완료된 ``pyupbit.Upbit`` 객체입니다.

    Raises:
        ValueError: API 키 둘 중 하나라도 없으면 발생합니다.
    """

    load_dotenv(env_file)
    access_key = os.getenv(access_key_var)
    secret_key = os.getenv(secret_key_var)

    if not access_key or not secret_key:
        raise ValueError(
            f"Missing Upbit API keys. Expected {access_key_var} and {secret_key_var}."
        )

    return pyupbit.Upbit(access_key, secret_key)


def list_krw_tickers(fiat: str = "KRW") -> list[str]:
    """지정한 원화 기준 마켓의 전체 티커 목록을 반환합니다."""

    tickers = pyupbit.get_tickers(fiat)
    return tickers or []


def get_ticker_prices(
    tickers: Iterable[str],
    sleep_seconds: float = 0.0,
    batch_size: int = 100,
) -> dict[str, float | None]:
    """여러 티커의 현재가를 조회해 딕셔너리로 반환합니다.

    Args:
        tickers: ``KRW-BTC`` 같은 티커 문자열 목록입니다.
        sleep_seconds: 요청 간격을 두고 싶을 때 사용할 대기 시간입니다.
        batch_size: 한 번에 조회할 티커 개수입니다.

    Returns:
        ``{티커: 현재가}`` 형태의 딕셔너리입니다. 조회 실패 시 값은 ``None``입니다.
    """

    unique_tickers = list(dict.fromkeys(tickers))
    prices: dict[str, float | None] = {}

    if not unique_tickers:
        return prices

    for ticker_chunk in _chunked(unique_tickers, batch_size):
        try:
            chunk_prices = pyupbit.get_current_price(ticker_chunk)
        except Exception:
            chunk_prices = None

        if isinstance(chunk_prices, dict):
            for ticker in ticker_chunk:
                price = chunk_prices.get(ticker)
                prices[ticker] = float(price) if price is not None else None
        elif len(ticker_chunk) == 1:
            price = chunk_prices
            prices[ticker_chunk[0]] = float(price) if price is not None else None
        else:
            for ticker in ticker_chunk:
                prices[ticker] = None

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return prices


def get_ohlcv(
    ticker: str,
    interval: str = "day",
    count: int = 200,
) -> pd.DataFrame:
    """특정 티커의 OHLCV 차트 데이터를 반환합니다.

    Args:
        ticker: ``KRW-BTC`` 같은 마켓 티커입니다.
        interval: ``day``, ``minute60`` 같은 캔들 간격입니다.
        count: 가져올 캔들 개수입니다.

    Returns:
        ``pyupbit``가 반환한 OHLCV 데이터프레임입니다.

    Raises:
        ValueError: 차트 데이터를 가져오지 못했을 때 발생합니다.
    """

    df = pyupbit.get_ohlcv(ticker, interval=interval, count=count)
    if df is None or df.empty:
        raise ValueError(f"Failed to fetch OHLCV data for {ticker} ({interval}).")
    return df


def get_top_coin_list(
    interval: str,
    top: int,
    market: str = "KRW",
    sleep_seconds: float = 0.05,
    cache_seconds: float = 60.0,
) -> list[str]:
    """최근 거래대금 기준 상위 코인 목록을 반환합니다.

    기존 스크립트와 동일하게 최근 2개 캔들의 ``종가 x 거래량`` 합계를 기준으로
    정렬합니다.
    """

    cache_key = (interval, top, market)
    cached_data = _TOP_COIN_LIST_CACHE.get(cache_key)
    now = time.time()

    if (
        cache_seconds > 0
        and cached_data is not None
        and now - cached_data[0] < cache_seconds
    ):
        return list(cached_data[1])

    coin_money: dict[str, float] = {}
    for ticker in list_krw_tickers(market):
        try:
            df = get_ohlcv(ticker, interval=interval)
            volume_money = (
                df["close"].iloc[-1] * df["volume"].iloc[-1]
                + df["close"].iloc[-2] * df["volume"].iloc[-2]
            )
            coin_money[ticker] = float(volume_money)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
        except Exception:
            continue

    sorted_tickers = sorted(
        coin_money.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    top_coin_list = [ticker for ticker, _ in sorted_tickers[:top]]

    if cache_seconds > 0:
        _TOP_COIN_LIST_CACHE[cache_key] = (now, list(top_coin_list))

    return top_coin_list


def get_current_price(ticker: str) -> float | None:
    """티커의 현재 시장가를 반환합니다."""

    return get_ticker_prices([ticker]).get(ticker)


def get_revenue_rate(
    balances: Iterable[Balance] | BalanceMap,
    ticker: str,
    sleep_seconds: float = 0.05,
    current_prices: dict[str, float | None] | None = None,
) -> float:
    """특정 보유 코인의 수익률(퍼센트)을 반환합니다."""

    balance_map = _get_balance_map(balances)
    value = balance_map.get(ticker)
    if value is None:
        return 0.0

    avg_buy_price = float(value.get("avg_buy_price", 0))
    if avg_buy_price == 0:
        return 0.0

    if current_prices is None:
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        current_prices = get_ticker_prices([ticker])

    now_price = current_prices.get(ticker)
    if now_price is None:
        return 0.0

    return (float(now_price) - avg_buy_price) * 100.0 / avg_buy_price


def get_total_real_money(balances: Iterable[Balance] | BalanceMap) -> float:
    """현재가 기준 총 평가금액을 반환합니다."""

    balance_map = _get_balance_map(balances)
    total = 0.0
    target_tickers: list[str] = []

    for value in balance_map.values():
        try:
            currency = value.get("currency")
            balance = float(value.get("balance", 0))
            locked = float(value.get("locked", 0))

            if currency == "KRW":
                total += balance + locked
                continue

            avg_buy_price = float(value.get("avg_buy_price", 0))
            if avg_buy_price == 0 or (balance == 0 and locked == 0):
                continue

        except Exception:
            continue

        target_tickers.append(_compose_balance_ticker(value))

    current_prices = get_ticker_prices(target_tickers)

    for ticker in target_tickers:
        value = balance_map[ticker]
        now_price = current_prices.get(ticker)
        if now_price is None or now_price == 0:
            continue

        balance = float(value.get("balance", 0))
        locked = float(value.get("locked", 0))
        total += float(now_price) * (balance + locked)

    return total


def get_total_real_money_safe(
    balances: Iterable[Balance] | BalanceMap,
    sleep_seconds: float = 0.1,
) -> float:
    """조금 더 느린 요청 간격으로 총 평가금액을 계산합니다.

    기존 ``getTotalRealMoney_save`` 함수 성격을 유지한 버전으로, 호출 속도를
    낮추고 싶을 때 사용할 수 있습니다.
    """

    balance_map = _get_balance_map(balances)
    total = 0.0
    target_tickers: list[str] = []

    for value in balance_map.values():
        try:
            currency = value.get("currency")
            balance = float(value.get("balance", 0))
            locked = float(value.get("locked", 0))

            if currency == "KRW":
                total += balance + locked
                continue

            avg_buy_price = float(value.get("avg_buy_price", 0))
            if avg_buy_price == 0 or (balance == 0 and locked == 0):
                continue

        except Exception:
            continue

        target_tickers.append(_compose_balance_ticker(value))

    current_prices = get_ticker_prices(target_tickers, sleep_seconds=sleep_seconds)

    for ticker in target_tickers:
        value = balance_map[ticker]
        now_price = current_prices.get(ticker)
        if now_price is None:
            continue

        balance = float(value.get("balance", 0))
        locked = float(value.get("locked", 0))
        total += float(now_price) * (balance + locked)

    return total


def buy_coin_market(
    upbit: pyupbit.Upbit,
    ticker: str,
    money: float,
    wait_seconds: float = 2.0,
) -> list[Balance]:
    """시장가 매수를 실행한 뒤 갱신된 잔고 목록을 반환합니다."""

    upbit.buy_market_order(ticker, money)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    return upbit.get_balances()


def sell_coin_market(
    upbit: pyupbit.Upbit,
    ticker: str,
    volume: float,
    wait_seconds: float = 2.0,
) -> list[Balance]:
    """시장가 매도를 실행한 뒤 갱신된 잔고 목록을 반환합니다."""

    upbit.sell_market_order(ticker, volume)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    return upbit.get_balances()


def buy_coin_limit(
    upbit: pyupbit.Upbit,
    ticker: str,
    price: float,
    volume: float,
) -> Any:
    """업비트 호가 단위에 맞춰 지정가 매수 주문을 넣습니다."""

    return upbit.buy_limit_order(ticker, pyupbit.get_tick_size(price), volume)


def sell_coin_limit(
    upbit: pyupbit.Upbit,
    ticker: str,
    price: float,
    volume: float,
) -> Any:
    """업비트 호가 단위에 맞춰 지정가 매도 주문을 넣습니다."""

    return upbit.sell_limit_order(ticker, pyupbit.get_tick_size(price), volume)


def cancel_coin_orders(
    upbit: pyupbit.Upbit,
    ticker: str,
    sleep_seconds: float = 0.1,
) -> list[Any]:
    """해당 티커에 걸린 모든 미체결 주문을 취소하고 응답 목록을 반환합니다."""

    responses: list[Any] = []
    orders_data = upbit.get_order(ticker) or []
    for order in orders_data:
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        responses.append(upbit.cancel_order(order["uuid"]))
    return responses
