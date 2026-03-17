"""结构化决策记录存储。"""

from __future__ import annotations

import json
from dataclasses import asdict

from autodoengine.core.types import DecisionPacket, DecisionResult
from .storage_paths import resolve_store_file


def _load_decisions() -> list[dict[str, object]]:
    file_path = resolve_store_file(kind="decisiondb", name="decisions.json")
    if not file_path.exists():
        return []
    return json.loads(file_path.read_text(encoding="utf-8"))


def _save_decisions(decisions: list[dict[str, object]]) -> None:
    file_path = resolve_store_file(kind="decisiondb", name="decisions.json")
    file_path.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")


def append_decision(result: DecisionResult, packet: DecisionPacket) -> None:
    """写入结构化决策记录。"""

    decisions = _load_decisions()
    packet_payload: dict[str, object]
    if hasattr(packet, "__dataclass_fields__"):
        packet_payload = asdict(packet)
    elif isinstance(packet, dict):
        packet_payload = dict(packet)
    else:
        packet_payload = {"raw_packet": str(packet)}

    decisions.append(
        {
            "decision": asdict(result),
            "packet": packet_payload,
        }
    )
    _save_decisions(decisions)


def get_decision(decision_uid: str) -> dict[str, object]:
    """读取单条决策记录。"""

    for item in _load_decisions():
        decision = item.get("decision") or {}
        if decision.get("decision_uid") == decision_uid:
            return item
    raise KeyError(f"决策不存在：{decision_uid}")


def list_task_decisions(task_uid: str) -> list[dict[str, object]]:
    """读取任务决策记录。"""

    return [item for item in _load_decisions() if (item.get("decision") or {}).get("task_uid") == task_uid]


def list_node_decisions(node_uid: str) -> list[dict[str, object]]:
    """读取节点决策记录。"""

    return [item for item in _load_decisions() if (item.get("decision") or {}).get("node_uid") == node_uid]

