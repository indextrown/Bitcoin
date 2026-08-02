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

    initial_capital: float = 1_000_000.0  # 시뮬레이션 시작 시 보유한 원화(KRW)입니다.
    fee_rate: float = 0.0005  # 매수·매도 주문마다 적용할 수수료 비율입니다. (0.0005 = 0.05%)
    cron_interval_minutes: int = 30  # 시뮬레이터가 봇을 실행한다고 가정할 간격(분)입니다.


@dataclass(frozen=True)
class V3Config:
    """V3 봇·백테스트·시각화가 공통으로 읽는 전체 설정입니다."""

    ticker: str = "KRW-ETH"  # 거래·분석할 업비트 마켓 티커입니다. 예: ``KRW-ETH``
    interval: str = "minute240"  # RSI 전략이 기준으로 삼을 업비트 캔들 간격입니다.
    strategy: StrategyConfig = field(default_factory=StrategyConfig)  # RSI·매수·매도 전략 설정입니다.
    backtest: BacktestConfig = field(default_factory=BacktestConfig)  # 시뮬레이터 전용 자금·수수료·크론 가정입니다.


def interval_to_timedelta(interval: str) -> timedelta:
    """업비트 캔들 간격 문자열을 해당 캔들 길이로 변환합니다.

    Args:
        interval: ``minute30``, ``minute240``, ``day``처럼 업비트가 사용하는
            캔들 간격 문자열입니다.

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


# 실제 봇은 ticker·interval·strategy만, 시뮬레이터는 backtest까지 함께 읽는 기본 V3 설정입니다.
V3_CONFIG = V3Config()
