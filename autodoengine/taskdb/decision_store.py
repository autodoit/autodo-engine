"""结构化决策记录存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from enum import Enum
from typing import Any

from autodoengine.core.enums import 中文持久化Mixin
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
        CREATE TABLE IF NOT EXISTS "决策记录" (
            uid_决策 TEXT PRIMARY KEY,
            uid_任务 TEXT NOT NULL,
            uid_节点 TEXT NOT NULL,
            "决策类型" TEXT NOT NULL,
            "选定动作" TEXT NOT NULL,
            "决策前任务状态" TEXT NOT NULL,
            "决策后任务状态" TEXT NOT NULL,
            uid_下一节点 TEXT,
            "原因编码" TEXT,
            "原因说明" TEXT,
            "决策执行方" TEXT,
            "决策参与成员JSON" TEXT,
            "决策模式" TEXT,
            "是否覆盖建议" INTEGER,
            "覆盖说明" TEXT,
            "拆分子项JSON" TEXT,
            "证据JSON" TEXT,
            "决策详情JSON" TEXT NOT NULL,
            "决策包JSON" TEXT NOT NULL,
            "创建时间" TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _to_db_jsonable(value: Any) -> Any:
    """把 dataclass/asdict 结果中的枚举递归转换为数据库中文值。"""

    if isinstance(value, 中文持久化Mixin):
        return value.db_value
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, dict):
        return {str(key): _to_db_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_db_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_db_jsonable(item) for item in value]
    return value


def _list_decisions() -> list[dict[str, object]]:
    with closing(_connect()) as connection, connection:
        rows = connection.execute('SELECT "决策详情JSON", "决策包JSON" FROM "决策记录" ORDER BY "创建时间"').fetchall()
    items: list[dict[str, object]] = []
    for row in rows:
        try:
            decision = json.loads(str(row["决策详情JSON"]))
        except Exception:
            decision = {}
        try:
            packet = json.loads(str(row["决策包JSON"]))
        except Exception:
            packet = {}
        items.append({"decision": decision, "packet": packet})
    return items


def append_decision(result: DecisionResult, packet: DecisionPacket) -> None:
    """写入结构化决策记录。"""

    decision_payload = _to_db_jsonable(asdict(result))
    packet_payload: dict[str, object]
    if hasattr(packet, "__dataclass_fields__"):
        packet_payload = _to_db_jsonable(asdict(packet))
    elif isinstance(packet, dict):
        packet_payload = _to_db_jsonable(dict(packet))
    else:
        packet_payload = {"raw_packet": str(packet)}

    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO "决策记录" (
                uid_决策, uid_任务, uid_节点, "决策类型", "选定动作",
                "决策前任务状态", "决策后任务状态", uid_下一节点,
                "原因编码", "原因说明", "决策执行方", "决策参与成员JSON",
                "决策模式", "是否覆盖建议", "覆盖说明",
                "拆分子项JSON", "证据JSON", "决策详情JSON", "决策包JSON", "创建时间"
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                str(decision_payload.get("uid_决策") or decision_payload.get("decision_uid") or ""),
                str(decision_payload.get("uid_任务") or decision_payload.get("task_uid") or ""),
                str(decision_payload.get("uid_节点") or decision_payload.get("node_uid") or ""),
                str(decision_payload.get("decision_type") or ""),
                str(decision_payload.get("selected_action") or ""),
                str(decision_payload.get("task_status_before") or ""),
                str(decision_payload.get("task_status_after") or ""),
                decision_payload.get("uid_下一节点") or decision_payload.get("next_node_uid"),
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
        if decision.get("uid_决策") == decision_uid or decision.get("decision_uid") == decision_uid:
            return item
    raise KeyError(f"决策不存在：{decision_uid}")


def list_task_decisions(task_uid: str) -> list[dict[str, object]]:
    """读取任务决策记录。"""

    return [
        item
        for item in _list_decisions()
        if (item.get("decision") or {}).get("uid_任务") == task_uid
        or (item.get("decision") or {}).get("task_uid") == task_uid
    ]


def list_node_decisions(node_uid: str) -> list[dict[str, object]]:
    """读取节点决策记录。"""

    return [
        item
        for item in _list_decisions()
        if (item.get("decision") or {}).get("uid_节点") == node_uid
        or (item.get("decision") or {}).get("node_uid") == node_uid
    ]

