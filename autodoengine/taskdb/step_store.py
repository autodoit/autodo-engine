"""任务步记录存储（SQLite）。"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import asdict

from autodoengine.core.enums import TaskAction, TaskStatus
from autodoengine.core.types import TaskStepRecord
from .storage_paths import get_runtime_store_files


def _get_db_path() -> str:
    return str(get_runtime_store_files()["tasks_db"])


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_get_db_path())
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "任务步骤" (
            uid_步骤 TEXT PRIMARY KEY,
            uid_运行 TEXT NOT NULL,
            uid_任务 TEXT NOT NULL,
            "uid_前节点" TEXT NOT NULL,
            "uid_后节点" TEXT NOT NULL,
            "选定动作" TEXT NOT NULL,
            "uid_选定边" TEXT,
            "前任务状态" TEXT NOT NULL,
            "后任务状态" TEXT NOT NULL,
            uid_决策 TEXT NOT NULL,
            "创建时间" TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()


def _load_steps() -> list[dict[str, object]]:
    with closing(_connect()) as connection, connection:
        rows = connection.execute('SELECT * FROM "任务步骤" ORDER BY "创建时间"').fetchall()
    return [dict(row) for row in rows]


def append_task_step(step_record: TaskStepRecord) -> None:
    """追加任务步记录。"""

    payload = asdict(step_record)
    payload["selected_action"] = step_record.selected_action.value
    payload["task_status_before"] = step_record.task_status_before.value
    payload["task_status_after"] = step_record.task_status_after.value
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO "任务步骤" (
                uid_步骤, uid_运行, uid_任务, "uid_前节点", "uid_后节点",
                "选定动作", "uid_选定边", "前任务状态", "后任务状态",
                uid_决策
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("uid_步骤") or payload["step_uid"]),
                str(payload.get("uid_运行") or payload["run_uid"]),
                str(payload.get("uid_任务") or payload["task_uid"]),
                str(payload.get("uid_前节点") or payload["node_uid_before"]),
                str(payload.get("uid_后节点") or payload["node_uid_after"]),
                step_record.selected_action.db_value,
                payload.get("uid_选定边") or payload.get("selected_edge_uid"),
                step_record.task_status_before.db_value,
                step_record.task_status_after.db_value,
                str(payload.get("uid_决策") or payload["decision_uid"]),
            ),
        )


def list_task_steps(task_uid: str) -> list[TaskStepRecord]:
    """读取任务全部步记录。"""

    records: list[TaskStepRecord] = []
    for item in _load_steps():
        if item.get("uid_任务") != task_uid and item.get("task_uid") != task_uid:
            continue
        selected_action = TaskAction.normalize(str(item.get("选定动作") or item.get("selected_action") or TaskAction.CONTINUE.value))
        status_before = TaskStatus.normalize(str(item.get("前任务状态") or item.get("task_status_before") or TaskStatus.READY.value))
        status_after = TaskStatus.normalize(str(item.get("后任务状态") or item.get("task_status_after") or TaskStatus.READY.value))
        records.append(
            TaskStepRecord(
                step_uid=str(item.get("uid_步骤") or item.get("step_uid")),
                run_uid=str(item.get("uid_运行") or item.get("run_uid")),
                task_uid=str(item.get("uid_任务") or item.get("task_uid")),
                node_uid_before=str(item.get("uid_前节点") or item.get("前节点UID") or item.get("node_uid_before")),
                node_uid_after=str(item.get("uid_后节点") or item.get("后节点UID") or item.get("node_uid_after")),
                selected_action=selected_action,
                selected_edge_uid=item.get("uid_选定边") or item.get("选定边UID"),
                task_status_before=status_before,
                task_status_after=status_after,
                decision_uid=str(item.get("uid_决策") or item.get("decision_uid")),
            )
        )
    return records


def list_run_steps(run_uid: str) -> list[TaskStepRecord]:
    """读取一次运行的全部步记录。"""

    records: list[TaskStepRecord] = []
    for item in _load_steps():
        if item.get("uid_运行") != run_uid and item.get("run_uid") != run_uid:
            continue
        selected_action = TaskAction.normalize(str(item.get("选定动作") or item.get("selected_action") or TaskAction.CONTINUE.value))
        status_before = TaskStatus.normalize(str(item.get("前任务状态") or item.get("task_status_before") or TaskStatus.READY.value))
        status_after = TaskStatus.normalize(str(item.get("后任务状态") or item.get("task_status_after") or TaskStatus.READY.value))
        records.append(
            TaskStepRecord(
                step_uid=str(item.get("uid_步骤") or item.get("step_uid")),
                run_uid=str(item.get("uid_运行") or item.get("run_uid")),
                task_uid=str(item.get("uid_任务") or item.get("task_uid")),
                node_uid_before=str(item.get("uid_前节点") or item.get("node_uid_before") or item.get("前节点UID")),
                node_uid_after=str(item.get("uid_后节点") or item.get("node_uid_after") or item.get("后节点UID")),
                selected_action=selected_action,
                selected_edge_uid=item.get("uid_选定边") or item.get("selected_edge_uid"),
                task_status_before=status_before,
                task_status_after=status_after,
                decision_uid=str(item.get("uid_决策") or item.get("decision_uid")),
            )
        )
    return records


def build_task_path(task_uid: str) -> list[str]:
    """重建任务轨迹路径。"""

    steps = list_task_steps(task_uid)
    if not steps:
        return []
    path = [steps[0].node_uid_before]
    path.extend(step.node_uid_after for step in steps)
    return path

