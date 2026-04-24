"""结构化决策记录存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from autodoengine.core.types import DecisionPacket, DecisionResult
from .storage_paths import get_runtime_store_files


def _get_db_path() -> str:
    return str(get_runtime_store_files()["decision_db"])

def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_get_db_path())
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS decisions (
            decision_uid TEXT PRIMARY KEY,
            task_uid TEXT NOT NULL,
            node_uid TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            selected_action TEXT NOT NULL,
            task_status_before TEXT NOT NULL,
            task_status_after TEXT NOT NULL,
            next_node_uid TEXT,
            reason_code TEXT,
            reason_text TEXT,
            decision_actor TEXT,
            decision_members_json TEXT,
            decision_mode TEXT,
            is_override_recommendation INTEGER,
            override_explanation TEXT,
            split_children_json TEXT,
            evidence_json TEXT,
            decision_json TEXT NOT NULL,
            packet_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _list_decisions() -> list[dict[str, object]]:
    with _connect() as connection:
        rows = connection.execute("SELECT decision_json, packet_json FROM decisions ORDER BY created_at").fetchall()
    items: list[dict[str, object]] = []
    for row in rows:
        try:
            decision = json.loads(str(row["decision_json"]))
        except Exception:
            decision = {}
        try:
            packet = json.loads(str(row["packet_json"]))
        except Exception:
            packet = {}
        items.append({"decision": decision, "packet": packet})
    return items


def append_decision(result: DecisionResult, packet: DecisionPacket) -> None:
    """写入结构化决策记录。"""

    decision_payload = asdict(result)
    packet_payload: dict[str, object]
    if hasattr(packet, "__dataclass_fields__"):
        packet_payload = asdict(packet)
    elif isinstance(packet, dict):
        packet_payload = dict(packet)
    else:
        packet_payload = {"raw_packet": str(packet)}

    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO decisions (
                decision_uid, task_uid, node_uid, decision_type, selected_action,
                task_status_before, task_status_after, next_node_uid,
                reason_code, reason_text, decision_actor, decision_members_json,
                decision_mode, is_override_recommendation, override_explanation,
                split_children_json, evidence_json, decision_json, packet_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                str(decision_payload.get("decision_uid") or ""),
                str(decision_payload.get("task_uid") or ""),
                str(decision_payload.get("node_uid") or ""),
                str(decision_payload.get("decision_type") or ""),
                str(decision_payload.get("selected_action") or ""),
                str(decision_payload.get("task_status_before") or ""),
                str(decision_payload.get("task_status_after") or ""),
                decision_payload.get("next_node_uid"),
                str(decision_payload.get("reason_code") or ""),
                str(decision_payload.get("reason_text") or ""),
                str(decision_payload.get("decision_actor") or ""),
                json.dumps(decision_payload.get("decision_members") or [], ensure_ascii=False),
                str(decision_payload.get("decision_mode") or ""),
                1 if bool(decision_payload.get("is_override_recommendation", False)) else 0,
                str(decision_payload.get("override_explanation") or ""),
                json.dumps(decision_payload.get("split_children") or [], ensure_ascii=False),
                json.dumps(decision_payload.get("evidence") or [], ensure_ascii=False),
                json.dumps(decision_payload, ensure_ascii=False),
                json.dumps(packet_payload, ensure_ascii=False),
            ),
        )


def get_decision(decision_uid: str) -> dict[str, object]:
    """读取单条决策记录。"""

    for item in _list_decisions():
        decision = item.get("decision") or {}
        if decision.get("decision_uid") == decision_uid:
            return item
    raise KeyError(f"决策不存在：{decision_uid}")


def list_task_decisions(task_uid: str) -> list[dict[str, object]]:
    """读取任务决策记录。"""

    return [item for item in _list_decisions() if (item.get("decision") or {}).get("task_uid") == task_uid]


def list_node_decisions(node_uid: str) -> list[dict[str, object]]:
    """读取节点决策记录。"""

    return [item for item in _list_decisions() if (item.get("decision") or {}).get("node_uid") == node_uid]

