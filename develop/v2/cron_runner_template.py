from __future__ import annotations

"""크론 실행용 V2 템플릿입니다.

이 파일은 보수적으로 만들어져 있습니다. ``DRY_RUN``을 바꾸고 주문 함수를
명시적으로 연결하기 전까지는 실제 주문을 넣지 않습니다.

노트북 기준 추천 크론 후보:

- 선물/마진/인버스 실행 환경:
  `v2_bear_hybrid_optimized`, 4시간봉, 30분마다 실행
- 업비트 현물 전용 환경:
  `spot_cash_guard_robust`, 60분봉, 15분마다 실행
- 하락장 현물 단타 보조:
  `bear_spot_quick_rebound`, 4시간봉, 30분마다 실행

운영 핵심은 크론을 캔들 주기보다 자주 실행하되, 완료된 캔들은 한 번만
처리하는 것입니다.
"""

from dataclasses import dataclass
from pathlib import Path
import json
import os
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from develop.upbit_develop_library import get_ohlcv  # noqa: E402


DRY_RUN = True
FEE_RATE = 0.0005
STATE_PATH = Path(__file__).with_name(".v2_cron_state.json")


@dataclass(frozen=True)
class CronStrategyConfig:
    name: str
    ticker: str = "KRW-BTC"
    interval: str = "minute60"
    ohlcv_count: int = 260
    allocation_ratio: float = 0.9
    rsi_min: float = 50.0
    volume_ratio_min: float = 1.2
    stop_loss_pct: float = -4.0


SPOT_CONFIG = CronStrategyConfig(
    name="spot_cash_guard_robust",
    interval="minute60",
    allocation_ratio=0.9,
    rsi_min=50.0,
    volume_ratio_min=1.5,
    stop_loss_pct=-3.0,
)

BEAR_QUICK_CONFIG = CronStrategyConfig(
    name="bear_spot_quick_rebound",
    interval="minute240",
    ohlcv_count=260,
    allocation_ratio=0.5,
    rsi_min=24.0,
    volume_ratio_min=1.0,
    stop_loss_pct=-2.5,
)

CONFIGS = {
    SPOT_CONFIG.name: SPOT_CONFIG,
    BEAR_QUICK_CONFIG.name: BEAR_QUICK_CONFIG,
}


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def calculate_rsi(close, period: int = 14):
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    avg_up = up.ewm(com=period - 1, min_periods=period).mean()
    avg_down = down.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_up / avg_down
    return 100 - (100 / (1 + rs))


def add_live_indicators(df):
    result = df.copy()
    result["ema50"] = result["close"].ewm(span=50, adjust=False).mean()
    result["ema200"] = result["close"].ewm(span=200, adjust=False).mean()
    result["rsi14"] = calculate_rsi(result["close"], 14)
    result["high20_prev"] = result["high"].rolling(20).max().shift(1)
    result["low10_prev"] = result["low"].rolling(10).min().shift(1)
    result["volume_ratio"] = result["volume"] / result["volume"].rolling(20).mean().shift(1)
    result["bull_regime"] = (result["close"] > result["ema200"]) & (result["ema50"] > result["ema200"])
    return result.dropna().copy()


def evaluate_spot_cash_guard_robust(df, config: CronStrategyConfig) -> dict[str, Any]:
    """마지막 완료 캔들 기준으로 신호를 반환합니다.

    pyupbit 분봉 데이터에는 진행 중인 현재 캔들이 포함될 수 있습니다.
    움직이는 캔들에서 주문하지 않도록 ``iloc[-2]``를 신호 캔들로 사용합니다.
    """

    signal = df.iloc[-2]
    breakout = signal["close"] > signal["high20_prev"]
    volume_confirmed = signal["volume_ratio"] >= config.volume_ratio_min
    should_buy = bool(
        signal["bull_regime"]
        and breakout
        and volume_confirmed
        and signal["rsi14"] >= config.rsi_min
    )
    return {
        "strategy": config.name,
        "ticker": config.ticker,
        "interval": config.interval,
        "signal_time": str(df.index[-2]),
        "close": float(signal["close"]),
        "rsi14": float(signal["rsi14"]),
        "volume_ratio": float(signal["volume_ratio"]),
        "should_buy": should_buy,
        "reason": "spot_cash_guard_robust_breakout" if should_buy else "no_signal",
    }


def evaluate_bear_spot_quick_rebound(df, config: CronStrategyConfig) -> dict[str, Any]:
    """하락장 과매도 반등을 짧게 먹는 현물 단타 신호를 반환합니다."""

    prev = df.iloc[-3]
    signal = df.iloc[-2]
    rsi_turn = prev["rsi14"] <= config.rsi_min and signal["rsi14"] > prev["rsi14"]
    strong_green = signal["close"] > signal["open"] and signal["close"] > prev["close"]
    volume_ok = signal["volume_ratio"] >= config.volume_ratio_min
    should_buy = bool((not signal["bull_regime"]) and rsi_turn and strong_green and volume_ok)
    return {
        "strategy": config.name,
        "ticker": config.ticker,
        "interval": config.interval,
        "signal_time": str(df.index[-2]),
        "close": float(signal["close"]),
        "rsi14": float(signal["rsi14"]),
        "prev_rsi14": float(prev["rsi14"]),
        "volume_ratio": float(signal["volume_ratio"]),
        "should_buy": should_buy,
        "reason": "bear_spot_quick_rebound" if should_buy else "no_signal",
    }


def main() -> None:
    strategy_name = os.getenv("V2_STRATEGY", SPOT_CONFIG.name)
    config = CONFIGS.get(strategy_name)
    if config is None:
        raise ValueError(f"Unknown V2_STRATEGY={strategy_name}. Expected one of {sorted(CONFIGS)}")

    df = add_live_indicators(get_ohlcv(config.ticker, interval=config.interval, count=config.ohlcv_count))
    if config.name == "bear_spot_quick_rebound":
        signal = evaluate_bear_spot_quick_rebound(df, config)
    else:
        signal = evaluate_spot_cash_guard_robust(df, config)

    state = load_state()
    state_key = f"{config.ticker}:{config.interval}:{config.name}"
    if state.get(state_key) == signal["signal_time"]:
        print(f"skip_duplicate_candle: {state_key} {signal['signal_time']}")
        return

    state[state_key] = signal["signal_time"]
    save_state(state)

    print(json.dumps(signal, ensure_ascii=False, indent=2))
    if DRY_RUN:
        print("DRY_RUN=True: no order submitted")
        return

    raise RuntimeError(
        "실주문 연결은 의도적으로 비활성화되어 있습니다. "
        "잔고, 주문 금액, 최소 주문금액, 매도/손절 처리를 먼저 연결하세요."
    )


if __name__ == "__main__":
    main()
