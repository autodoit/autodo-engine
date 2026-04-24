"""任务步记录存储（SQLite）。"""

from __future__ import annotations

import sqlite3
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
        CREATE TABLE IF NOT EXISTS aoe_task_steps (
            step_uid TEXT PRIMARY KEY,
            run_uid TEXT NOT NULL,
            task_uid TEXT NOT NULL,
            node_uid_before TEXT NOT NULL,
            node_uid_after TEXT NOT NULL,
            selected_action TEXT NOT NULL,
            selected_edge_uid TEXT,
            task_status_before TEXT NOT NULL,
            task_status_after TEXT NOT NULL,
            decision_uid TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()


def _load_steps() -> list[dict[str, object]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM aoe_task_steps ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]


def append_task_step(step_record: TaskStepRecord) -> None:
    """追加任务步记录。"""

    payload = asdict(step_record)
    payload["selected_action"] = step_record.selected_action.value
    payload["task_status_before"] = step_record.task_status_before.value
    payload["task_status_after"] = step_record.task_status_after.value
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO aoe_task_steps (
                step_uid, run_uid, task_uid, node_uid_before, node_uid_after,
                selected_action, selected_edge_uid, task_status_before, task_status_after,
                decision_uid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["step_uid"]),
                str(payload["run_uid"]),
                str(payload["task_uid"]),
                str(payload["node_uid_before"]),
                str(payload["node_uid_after"]),
                str(payload["selected_action"]),
                payload.get("selected_edge_uid"),
                str(payload["task_status_before"]),
                str(payload["task_status_after"]),
                str(payload["decision_uid"]),
            ),
        )


def list_task_steps(task_uid: str) -> list[TaskStepRecord]:
    """读取任务全部步记录。"""

    records: list[TaskStepRecord] = []
    for item in _load_steps():
        if item["task_uid"] != task_uid:
            continue
        records.append(
            TaskStepRecord(
                step_uid=str(item["step_uid"]),
                run_uid=str(item["run_uid"]),
                task_uid=str(item["task_uid"]),
                node_uid_before=str(item["node_uid_before"]),
                node_uid_after=str(item["node_uid_after"]),
                selected_action=TaskAction(str(item["selected_action"])),
                selected_edge_uid=item.get("selected_edge_uid"),
                task_status_before=TaskStatus(str(item["task_status_before"])),
                task_status_after=TaskStatus(str(item["task_status_after"])),
                decision_uid=str(item["decision_uid"]),
            )
        )
    return records


def list_run_steps(run_uid: str) -> list[TaskStepRecord]:
    """读取一次运行的全部步记录。"""

    records: list[TaskStepRecord] = []
    for item in _load_steps():
        if item["run_uid"] != run_uid:
            continue
        records.append(
            TaskStepRecord(
                step_uid=str(item["step_uid"]),
                run_uid=str(item["run_uid"]),
                task_uid=str(item["task_uid"]),
                node_uid_before=str(item["node_uid_before"]),
                node_uid_after=str(item["node_uid_after"]),
                selected_action=TaskAction(str(item["selected_action"])),
                selected_edge_uid=item.get("selected_edge_uid"),
                task_status_before=TaskStatus(str(item["task_status_before"])),
                task_status_after=TaskStatus(str(item["task_status_after"])),
                decision_uid=str(item["decision_uid"]),
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

