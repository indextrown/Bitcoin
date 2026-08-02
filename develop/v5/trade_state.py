"""V5가 시장가 매수와 지정가 매도 사이의 상태를 이어가기 위한 저장 도구입니다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path


@dataclass(frozen=True)
class ScalpState:
    """V5의 주문 진행 상태와 현재 단타 포지션 정보를 저장합니다."""

    status: str = "FLAT"  # ``FLAT``, ``ENTRY_PENDING``, ``TARGET_OPEN``, ``EXIT_PENDING`` 중 하나입니다.
    entry_order_uuid: str | None = None  # 시장가 매수 주문 조회에 사용할 업비트 UUID입니다.
    entry_cost_krw: float = 0.0  # 시장가 매수에 요청한 원화 금액입니다.
    entry_time: datetime | None = None  # 시장가 매수가 체결된 것으로 확인한 시각입니다.
    acquired_volume: float = 0.0  # 매수 수수료 뒤 지정가 매도에 사용할 코인 수량입니다.
    entry_price: float = 0.0  # 매수 체결 수량으로 계산한 평균 진입가입니다.
    target_order_uuid: str | None = None  # 업비트 지정가 목표 매도 주문 UUID입니다.
    target_price: float = 0.0  # 목표 순이익을 만족하도록 계산한 지정가 매도 가격입니다.


def load_trade_state(path: Path) -> ScalpState:
    """V5 상태 JSON을 읽고, 없거나 손상됐으면 빈 포지션을 반환합니다.

    Args:
        path: V5 주문 진행 상태를 저장한 JSON 파일 경로입니다.

    Returns:
        직전 상태 또는 안전한 빈 포지션 상태입니다.
    """

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        entry_time = value.get("entry_time")
        return ScalpState(
            status=str(value.get("status", "FLAT")),
            entry_order_uuid=value.get("entry_order_uuid"),
            entry_cost_krw=float(value.get("entry_cost_krw", 0.0)),
            entry_time=datetime.fromisoformat(entry_time) if entry_time else None,
            acquired_volume=float(value.get("acquired_volume", 0.0)),
            entry_price=float(value.get("entry_price", 0.0)),
            target_order_uuid=value.get("target_order_uuid"),
            target_price=float(value.get("target_price", 0.0)),
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return ScalpState()


def save_trade_state(path: Path, state: ScalpState) -> None:
    """V5 상태를 임시 파일을 거쳐 원자적으로 저장합니다.

    Args:
        path: 상태 JSON을 저장할 파일 경로입니다.
        state: 저장할 V5 주문 진행 상태입니다.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": state.status,
        "entry_order_uuid": state.entry_order_uuid,
        "entry_cost_krw": state.entry_cost_krw,
        "entry_time": state.entry_time.isoformat() if state.entry_time else None,
        "acquired_volume": state.acquired_volume,
        "entry_price": state.entry_price,
        "target_order_uuid": state.target_order_uuid,
        "target_price": state.target_price,
    }
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(path)
