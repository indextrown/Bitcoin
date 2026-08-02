"""V5 단타 봇과 백테스트가 함께 사용하는 설정입니다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from develop.v5.trade_logic import StrategyConfig


@dataclass(frozen=True)
class BacktestConfig:
    """실거래와 분리된 V5 백테스트 체결·실행 가정값입니다."""

    initial_capital: float = 300_000.0  # 시뮬레이션 시작 시 V5에 배정한 원화(KRW)입니다.
    cron_interval_minutes: int = 5  # 시뮬레이터가 V5를 실행한다고 가정할 간격(분)입니다.


@dataclass(frozen=True)
class V5Config:
    """V5 단타 봇·백테스트·시각화가 공통으로 읽는 전체 설정입니다."""

    ticker: str = "KRW-BTC"  # V4의 ETH와 분리해 V5가 단타할 업비트 마켓 티커입니다.
    interval: str = "minute5"  # RSI·볼린저 밴드 신호를 계산할 완료 캔들 간격입니다.
    fee_rate: float = 0.0005  # 실제 목표가와 백테스트 체결이 공통으로 사용할 주문당 수수료 비율입니다.
    strategy: StrategyConfig = field(default_factory=StrategyConfig)  # V5 진입·청산 규칙입니다.
    backtest: BacktestConfig = field(default_factory=BacktestConfig)  # 시뮬레이터 전용 자금·수수료·크론 가정입니다.


def interval_to_timedelta(interval: str) -> timedelta:
    """업비트 캔들 간격 문자열을 해당 캔들 길이로 변환합니다.

    Args:
        interval: ``minute5``, ``minute30``, ``day``처럼 업비트가 사용하는 캔들 간격입니다.

    Returns:
        입력 간격이 나타내는 시간 길이입니다.

    Raises:
        ValueError: 지원하지 않거나 분 단위 숫자가 잘못된 간격일 때 발생합니다.
    """

    if interval == "day":
        return timedelta(days=1)
    if interval.startswith("minute"):
        try:
            minutes = int(interval.removeprefix("minute"))
        except ValueError as error:
            raise ValueError(f"Invalid minute interval: {interval}") from error
        if minutes > 0:
            return timedelta(minutes=minutes)
    raise ValueError(f"Unsupported interval: {interval}")


def validate_v5_ticker(ticker: str) -> None:
    """V5가 V4의 ETH 전용 전략과 같은 티커를 사용하지 않는지 확인합니다.

    Args:
        ticker: V5에 설정하려는 업비트 마켓 티커입니다.

    Raises:
        ValueError: ETH 티커 또는 KRW 마켓 형식이 아닌 티커일 때 발생합니다.
    """

    if not ticker.startswith("KRW-"):
        raise ValueError("V5 ticker must be a KRW market ticker.")
    if ticker == "KRW-ETH":
        raise ValueError("V5 must use a ticker other than KRW-ETH, which is reserved for V4.")


# 실제 봇은 ticker·interval·strategy만, 시뮬레이터는 backtest까지 함께 읽는 기본 V5 설정입니다.
V5_CONFIG = V5Config()
