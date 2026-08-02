"""V3 봇과 백테스트가 함께 사용하는 설정입니다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from develop.v3.trade_logic import StrategyConfig


@dataclass(frozen=True)
class BacktestConfig:
    """실거래와 분리된 백테스트 체결·실행 가정값입니다.

    ``cron_interval_minutes``는 백테스트에서만 사용하는 봇 실행 주기 가정입니다.
    실제 ``btc_bot.py``의 실행 주기는 서버의 crontab이 결정하므로 이 값을 읽지
    않습니다.
    """

    initial_capital: float = 1_000_000.0
    fee_rate: float = 0.0005
    cron_interval_minutes: int = 30


@dataclass(frozen=True)
class V3Config:
    """V3 봇·백테스트·시각화가 공통으로 읽는 전체 설정입니다."""

    ticker: str = "KRW-ETH"
    interval: str = "minute240"
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)


def interval_to_timedelta(interval: str) -> timedelta:
    """업비트 캔들 간격 문자열을 해당 캔들 길이로 변환합니다."""

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


V3_CONFIG = V3Config()
