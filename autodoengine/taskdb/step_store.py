"""任务步记录存储。"""

from __future__ import annotations

import json
from dataclasses import asdict

from autodoengine.core.enums import TaskAction, TaskStatus
from autodoengine.core.types import TaskStepRecord
from .storage_paths import resolve_store_file


def _load_steps() -> list[dict[str, object]]:
    file_path = resolve_store_file(kind="taskdb", name="task_steps.json")
    if not file_path.exists():
        return []
    return json.loads(file_path.read_text(encoding="utf-8"))


def _save_steps(steps: list[dict[str, object]]) -> None:
    file_path = resolve_store_file(kind="taskdb", name="task_steps.json")
    file_path.write_text(json.dumps(steps, ensure_ascii=False, indent=2), encoding="utf-8")


def append_task_step(step_record: TaskStepRecord) -> None:
    """追加任务步记录。"""

    steps = _load_steps()
    payload = asdict(step_record)
    payload["selected_action"] = step_record.selected_action.value
    payload["task_status_before"] = step_record.task_status_before.value
    payload["task_status_after"] = step_record.task_status_after.value
    steps.append(payload)
    _save_steps(steps)


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

