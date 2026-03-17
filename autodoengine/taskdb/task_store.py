"""任务主表读写。"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from uuid import uuid4
from typing import Any

from autodoengine.core.enums import TaskStatus
from .storage_paths import resolve_store_file


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_tasks() -> list[dict[str, Any]]:
    file_path = resolve_store_file(kind="taskdb", name="tasks.json")
    if not file_path.exists():
        return []
    return json.loads(file_path.read_text(encoding="utf-8"))


def _save_tasks(tasks: list[dict[str, Any]]) -> None:
    file_path = resolve_store_file(kind="taskdb", name="tasks.json")
    file_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def create_task(*, title: str, goal_text: str, current_node_uid: str, parent_task_uid: str | None = None) -> dict[str, Any]:
    """创建任务。"""

    tasks = _load_tasks()
    task_uid = f"task-{uuid4().hex[:12]}"
    now = _now_iso()
    task = {
        "task_uid": task_uid,
        "title": title,
        "goal_text": goal_text,
        "status": TaskStatus.READY.value,
        "current_node_uid": current_node_uid,
        "current_affair_uid": None,
        "parent_task_uid": parent_task_uid,
        "retry_count": 0,
        "max_retry": 2,
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }
    tasks.append(task)
    _save_tasks(tasks)
    return task


def get_task(task_uid: str) -> dict[str, Any]:
    """读取单个任务。"""

    for task in _load_tasks():
        if task["task_uid"] == task_uid:
            return task
    raise KeyError(f"任务不存在：{task_uid}")


def list_tasks(*, status: TaskStatus | None = None) -> list[dict[str, Any]]:
    """按状态列出任务。"""

    tasks = _load_tasks()
    if status is None:
        return tasks
    return [task for task in tasks if task["status"] == status.value]


def update_task_status(task_uid: str, status: TaskStatus) -> None:
    """更新任务状态。"""

    tasks = _load_tasks()
    for task in tasks:
        if task["task_uid"] == task_uid:
            task["status"] = status.value
            task["updated_at"] = _now_iso()
            _save_tasks(tasks)
            return
    raise KeyError(f"任务不存在：{task_uid}")


def update_task_cursor(task_uid: str, *, current_node_uid: str, current_affair_uid: str | None) -> None:
    """更新任务当前位置。"""

    tasks = _load_tasks()
    for task in tasks:
        if task["task_uid"] == task_uid:
            task["current_node_uid"] = current_node_uid
            task["current_affair_uid"] = current_affair_uid
            task["updated_at"] = _now_iso()
            _save_tasks(tasks)
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

    tasks = _load_tasks()
    for task in tasks:
        if task["task_uid"] == task_uid:
            task["retry_count"] = int(task.get("retry_count", 0)) + 1
            task["updated_at"] = _now_iso()
            _save_tasks(tasks)
            return
    raise KeyError(f"任务不存在：{task_uid}")


def update_task_metadata(task_uid: str, metadata: dict[str, Any], *, merge: bool = True) -> None:
    """更新任务元数据。"""

    tasks = _load_tasks()
    for task in tasks:
        if task["task_uid"] == task_uid:
            if merge:
                current = dict(task.get("metadata") or {})
                current.update(metadata)
                task["metadata"] = current
            else:
                task["metadata"] = dict(metadata)
            task["updated_at"] = _now_iso()
            _save_tasks(tasks)
            return
    raise KeyError(f"任务不存在：{task_uid}")


def list_tasks_by_parent(parent_task_uid: str) -> list[dict[str, Any]]:
    """按父任务 UID 列出子任务。"""

    return [item for item in _load_tasks() if item.get("parent_task_uid") == parent_task_uid]

