"""任务状态机。"""

from __future__ import annotations

from autodoengine.core.enums import TaskStatus
from autodoengine.core.errors import TaskTransitionError

_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.RUNNING,
        TaskStatus.SUSPENDED,
        TaskStatus.BLOCKED,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.SUSPENDED: {TaskStatus.READY, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED: {TaskStatus.READY, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def validate_transition(from_status: TaskStatus, to_status: TaskStatus) -> None:
    """校验状态迁移是否合法。"""

    if to_status not in _ALLOWED_TRANSITIONS[from_status]:
        raise TaskTransitionError(f"非法状态迁移：{from_status.value} -> {to_status.value}")


def apply_transition(task_uid: str, from_status: TaskStatus, to_status: TaskStatus) -> None:
    """执行状态迁移。"""

    validate_transition(from_status, to_status)
    from . import task_store

    task_store.update_task_status(task_uid, to_status)


def can_resume_task(task_status: TaskStatus, child_statuses: list[TaskStatus]) -> bool:
    """判断父任务是否可恢复。"""

    if task_status != TaskStatus.SUSPENDED:
        return False
    return all(status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED} for status in child_statuses)


def can_split_task(task_status: TaskStatus) -> bool:
    """判断当前任务是否可分裂。"""

    return task_status == TaskStatus.RUNNING


def can_complete_task(task_status: TaskStatus) -> bool:
    """判断当前任务是否可完成。"""

    return task_status == TaskStatus.RUNNING

