"""任务主表读写（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from uuid import uuid4
from typing import Any

from autodoengine.core.enums import TaskStatus
from autodoengine.utils.time_utils import now_iso
from .storage_paths import get_runtime_store_files


def _now_iso() -> str:
    return now_iso()


def _get_db_path() -> str:
    return str(get_runtime_store_files()["tasks_db"])


def _connect() -> sqlite3.Connection:
    db_path = _get_db_path()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "任务运行" (
            uid_任务 TEXT PRIMARY KEY,
            uid_工作流 TEXT NOT NULL DEFAULT '',
            "节点编码" TEXT NOT NULL DEFAULT '',
            "闸门编码" TEXT NOT NULL DEFAULT '',
            "动作决策" TEXT NOT NULL DEFAULT '',
            "运行状态" TEXT NOT NULL DEFAULT '',
            "工作区根路径" TEXT NOT NULL DEFAULT '',
            "输入摘要JSON" TEXT NOT NULL DEFAULT '{}',
            "输出摘要JSON" TEXT NOT NULL DEFAULT '{}',
            "开始时间" TEXT NOT NULL DEFAULT '',
            "结束时间" TEXT NOT NULL DEFAULT '',
            "操作人" TEXT NOT NULL DEFAULT '',
            "备注" TEXT NOT NULL DEFAULT '',
            "标题" TEXT NOT NULL DEFAULT '',
            "目标说明" TEXT NOT NULL DEFAULT '',
            "uid_当前节点" TEXT NOT NULL DEFAULT '',
            "uid_当前事务" TEXT,
            "uid_父任务" TEXT,
            "重试次数" INTEGER NOT NULL DEFAULT 0,
            "最大重试次数" INTEGER NOT NULL DEFAULT 2,
            "元数据JSON" TEXT NOT NULL DEFAULT '{}',
            "创建时间" TEXT NOT NULL DEFAULT '',
            "更新时间" TEXT NOT NULL DEFAULT ''
        )
        """
    )
    for column_name, column_def in {
        "uid_工作流": "TEXT NOT NULL DEFAULT ''",
        "节点编码": "TEXT NOT NULL DEFAULT ''",
        "闸门编码": "TEXT NOT NULL DEFAULT ''",
        "动作决策": "TEXT NOT NULL DEFAULT ''",
        "运行状态": "TEXT NOT NULL DEFAULT ''",
        "工作区根路径": "TEXT NOT NULL DEFAULT ''",
        "输入摘要JSON": "TEXT NOT NULL DEFAULT '{}'",
        "输出摘要JSON": "TEXT NOT NULL DEFAULT '{}'",
        "开始时间": "TEXT NOT NULL DEFAULT ''",
        "结束时间": "TEXT NOT NULL DEFAULT ''",
        "操作人": "TEXT NOT NULL DEFAULT ''",
        "备注": "TEXT NOT NULL DEFAULT ''",
        "标题": "TEXT NOT NULL DEFAULT ''",
        "目标说明": "TEXT NOT NULL DEFAULT ''",
        "uid_当前节点": "TEXT NOT NULL DEFAULT ''",
        "uid_当前事务": "TEXT",
        "uid_父任务": "TEXT",
        "重试次数": "INTEGER NOT NULL DEFAULT 0",
        "最大重试次数": "INTEGER NOT NULL DEFAULT 2",
        "元数据JSON": "TEXT NOT NULL DEFAULT '{}'",
        "创建时间": "TEXT NOT NULL DEFAULT ''",
        "更新时间": "TEXT NOT NULL DEFAULT ''",
    }.items():
        _ensure_column(connection, "任务运行", column_name, column_def)
    connection.commit()


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_def: str) -> None:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    existing = {str(row[1]) for row in rows if len(row) > 1}
    if column_name in existing:
        return
    connection.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_def}')


def _quote_identifier(name: str) -> str:
    return f'"{name}"'


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f'PRAGMA table_info({_quote_identifier(table_name)})').fetchall()
    return {str(row[1]) for row in rows if len(row) > 1}


def _resolve_task_uid_column(connection: sqlite3.Connection) -> str:
    columns = _table_columns(connection, "任务运行")
    if "uid_任务" in columns:
        return "uid_任务"
    if "task_uid" in columns:
        return "task_uid"
    return "uid_任务"


def _resolve_workflow_uid_column(connection: sqlite3.Connection) -> str:
    columns = _table_columns(connection, "任务运行")
    if "uid_工作流" in columns:
        return "uid_工作流"
    if "workflow_uid" in columns:
        return "workflow_uid"
    return "uid_工作流"


def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    raw_metadata = payload.get("元数据JSON") or payload.get("metadata_json") or "{}"
    try:
        metadata = json.loads(raw_metadata)
    except Exception:
        metadata = {}
    status = TaskStatus.normalize(str(payload.get("运行状态") or payload.get("status") or TaskStatus.READY.value))
    return {
        "uid_任务": str(payload.get("uid_任务") or payload.get("task_uid") or ""),
        "task_uid": str(payload.get("uid_任务") or payload.get("task_uid") or ""),
        "title": str(payload.get("标题") or payload.get("title") or ""),
        "goal_text": str(payload.get("目标说明") or payload.get("goal_text") or ""),
        "status": status.value,
        "运行状态": status.db_value,
        "uid_当前节点": str(payload.get("uid_当前节点") or payload.get("当前节点UID") or payload.get("current_node_uid") or payload.get("节点编码") or payload.get("node_code") or ""),
        "current_node_uid": str(payload.get("uid_当前节点") or payload.get("当前节点UID") or payload.get("current_node_uid") or payload.get("节点编码") or payload.get("node_code") or ""),
        "uid_当前事务": payload.get("uid_当前事务") or payload.get("当前事务UID") or payload.get("current_affair_uid"),
        "current_affair_uid": payload.get("uid_当前事务") or payload.get("当前事务UID") or payload.get("current_affair_uid"),
        "uid_父任务": payload.get("uid_父任务") or payload.get("父任务UID") or payload.get("parent_task_uid"),
        "parent_task_uid": payload.get("uid_父任务") or payload.get("父任务UID") or payload.get("parent_task_uid"),
        "retry_count": int(payload.get("重试次数") or payload.get("retry_count") or 0),
        "max_retry": int(payload.get("最大重试次数") or payload.get("max_retry") or 2),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": str(payload.get("创建时间") or payload.get("created_at") or payload.get("开始时间") or ""),
        "updated_at": str(payload.get("更新时间") or payload.get("updated_at") or payload.get("结束时间") or ""),
    }


def create_task(*, title: str, goal_text: str, current_node_uid: str, parent_task_uid: str | None = None) -> dict[str, Any]:
    """创建任务。"""

    task_uid = f"task-{uuid4().hex[:12]}"
    workflow_uid = f"wf-{task_uid}"
    now = _now_iso()
    with closing(_connect()) as connection, connection:
        columns = _table_columns(connection, "任务运行")
        task_uid_column = _resolve_task_uid_column(connection)
        workflow_uid_columns: list[str] = []
        if "workflow_uid" in columns:
            workflow_uid_columns.append("workflow_uid")
        if "uid_工作流" in columns:
            workflow_uid_columns.append("uid_工作流")
        if not workflow_uid_columns:
            workflow_uid_columns.append(_resolve_workflow_uid_column(connection))

        insert_columns = [
            task_uid_column,
            *workflow_uid_columns,
            "节点编码",
            "闸门编码",
            "动作决策",
            "运行状态",
            "工作区根路径",
            "输入摘要JSON",
            "输出摘要JSON",
            "开始时间",
            "结束时间",
            "操作人",
            "备注",
            "标题",
            "目标说明",
            "uid_当前节点",
            "uid_当前事务",
            "uid_父任务",
            "重试次数",
            "最大重试次数",
            "元数据JSON",
            "创建时间",
            "更新时间",
        ]
        insert_values: list[object] = [
            task_uid,
            *[workflow_uid for _ in workflow_uid_columns],
            current_node_uid,
            "",
            "",
            TaskStatus.READY.db_value,
            "",
            "{}",
            "{}",
            now,
            now,
            "",
            "",
            title,
            goal_text,
            current_node_uid,
            None,
            parent_task_uid,
            0,
            2,
            "{}",
            now,
            now,
        ]
        column_sql = ", ".join(_quote_identifier(item) for item in insert_columns)
        placeholder_sql = ", ".join("?" for _ in insert_columns)
        connection.execute(
            f"""
            INSERT INTO "任务运行" ({column_sql}) VALUES ({placeholder_sql})
            """,
            insert_values,
        )
        row = connection.execute(
            f'SELECT * FROM "任务运行" WHERE {_quote_identifier(task_uid_column)}=?',
            (task_uid,),
        ).fetchone()
    if row is None:
        raise KeyError(f"任务创建失败：{task_uid}")
    return _row_to_task(row)


def get_task(task_uid: str) -> dict[str, Any]:
    """读取单个任务。"""

    with closing(_connect()) as connection, connection:
        task_uid_column = _resolve_task_uid_column(connection)
        row = connection.execute(
            f'SELECT * FROM "任务运行" WHERE {_quote_identifier(task_uid_column)}=?',
            (task_uid,),
        ).fetchone()
    if row is not None:
        return _row_to_task(row)
    raise KeyError(f"任务不存在：{task_uid}")


def list_tasks(*, status: TaskStatus | None = None) -> list[dict[str, Any]]:
    """按状态列出任务。"""

    with closing(_connect()) as connection, connection:
        if status is None:
            rows = connection.execute('SELECT * FROM "任务运行" ORDER BY "创建时间"').fetchall()
        else:
            rows = connection.execute(
                'SELECT * FROM "任务运行" WHERE "运行状态"=? ORDER BY "创建时间"', (status.db_value,)
            ).fetchall()
    return [_row_to_task(row) for row in rows]


def update_task_status(task_uid: str, status: TaskStatus) -> None:
    """更新任务状态。"""

    now = _now_iso()
    with closing(_connect()) as connection, connection:
        task_uid_column = _resolve_task_uid_column(connection)
        cursor = connection.execute(
            f'UPDATE "任务运行" SET "运行状态"=?, "更新时间"=?, "结束时间"=? WHERE {_quote_identifier(task_uid_column)}=?',
            (status.db_value, now, now, task_uid),
        )
        if cursor.rowcount:
            return
    raise KeyError(f"任务不存在：{task_uid}")


def update_task_cursor(task_uid: str, *, current_node_uid: str, current_affair_uid: str | None) -> None:
    """更新任务当前位置。"""

    now = _now_iso()
    with closing(_connect()) as connection, connection:
        task_uid_column = _resolve_task_uid_column(connection)
        cursor = connection.execute(
            f"""
            UPDATE "任务运行"
            SET "uid_当前节点"=?, "uid_当前事务"=?, "节点编码"=?, "更新时间"=?
            WHERE {_quote_identifier(task_uid_column)}=?
            """,
            (current_node_uid, current_affair_uid, current_node_uid, now, task_uid),
        )
        if cursor.rowcount:
            return
    raise KeyError(f"任务不存在：{task_uid}")


def mark_task_completed(task_uid: str) -> None:
    """将任务标记为已完成。"""

    update_task_status(task_uid, TaskStatus.COMPLETED)


def mark_task_failed(task_uid: str) -> None:
    """将任务标记为失败。"""

    update_task_status(task_uid, TaskStatus.FAILED)


def mark_task_cancelled(task_uid: str) -> None:
    """将任务标记为已取消。"""

    update_task_status(task_uid, TaskStatus.CANCELLED)


def bump_retry_count(task_uid: str) -> None:
    """递增任务重试计数。"""

    now = _now_iso()
    with closing(_connect()) as connection, connection:
        task_uid_column = _resolve_task_uid_column(connection)
        cursor = connection.execute(
            f"""
            UPDATE "任务运行"
            SET "重试次数" = COALESCE("重试次数", 0) + 1, "更新时间"=?
            WHERE {_quote_identifier(task_uid_column)}=?
            """,
            (now, task_uid),
        )
        if cursor.rowcount:
            return
    raise KeyError(f"任务不存在：{task_uid}")


def update_task_metadata(task_uid: str, metadata: dict[str, Any], *, merge: bool = True) -> None:
    """更新任务元数据。"""

    with closing(_connect()) as connection, connection:
        task_uid_column = _resolve_task_uid_column(connection)
        row = connection.execute(
            f'SELECT "元数据JSON" FROM "任务运行" WHERE {_quote_identifier(task_uid_column)}=?',
            (task_uid,),
        ).fetchone()
        if row is None:
            raise KeyError(f"任务不存在：{task_uid}")
        current: dict[str, Any] = {}
        raw_metadata = row[0] if len(row) > 0 else "{}"
        try:
            parsed = json.loads(raw_metadata or "{}")
            if isinstance(parsed, dict):
                current = parsed
        except Exception:
            current = {}

        next_metadata = dict(metadata)
        if merge:
            current.update(next_metadata)
            next_metadata = current

        connection.execute(
            f'UPDATE "任务运行" SET "元数据JSON"=?, "更新时间"=? WHERE {_quote_identifier(task_uid_column)}=?',
            (json.dumps(next_metadata, ensure_ascii=False), _now_iso(), task_uid),
        )
        return


def list_tasks_by_parent(parent_task_uid: str) -> list[dict[str, Any]]:
    """按父任务 UID 列出子任务。"""

    with closing(_connect()) as connection, connection:
        rows = connection.execute(
            'SELECT * FROM "任务运行" WHERE "uid_父任务"=? ORDER BY "创建时间"',
            (parent_task_uid,),
        ).fetchall()
    return [_row_to_task(row) for row in rows]

