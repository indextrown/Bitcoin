"""V4.1 실제 봇이 손절 쿨다운을 이어가기 위해 저장하는 작은 상태 파일 도구입니다."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path


@dataclass(frozen=True)
class TradeState:
    """프로세스가 종료된 뒤에도 유지해야 하는 V4.1 매매 상태입니다."""

    last_stop_loss_time: datetime | None = None  # 가장 최근 손절이 실제 체결된 시각입니다.


def load_trade_state(path: Path) -> TradeState:
    """상태 파일에서 최근 손절 시각을 읽고, 없거나 손상됐으면 빈 상태를 반환합니다.

    Args:
        path: ``last_stop_loss_time``을 저장한 JSON 상태 파일 경로입니다.

    Returns:
        읽은 최근 손절 시각 또는 쿨다운이 없는 빈 상태입니다.
    """

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        raw_time = value.get("last_stop_loss_time")
        return TradeState(datetime.fromisoformat(raw_time) if raw_time else None)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return TradeState()


def save_trade_state(path: Path, state: TradeState) -> None:
    """최근 손절 시각을 JSON으로 원자적으로 저장합니다.

    Args:
        path: 상태 JSON을 저장할 경로입니다.
        state: 저장할 최근 손절 시각을 담은 V4.1 상태입니다.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    payload["last_stop_loss_time"] = (
        state.last_stop_loss_time.isoformat() if state.last_stop_loss_time else None
    )
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(path)
