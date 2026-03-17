"""任务关系存储。"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from uuid import uuid4

from .storage_paths import resolve_store_file


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_relations() -> list[dict[str, str]]:
    file_path = resolve_store_file(kind="taskdb", name="task_relations.json")
    if not file_path.exists():
        return []
    return json.loads(file_path.read_text(encoding="utf-8"))


def _save_relations(relations: list[dict[str, str]]) -> None:
    file_path = resolve_store_file(kind="taskdb", name="task_relations.json")
    file_path.write_text(json.dumps(relations, ensure_ascii=False, indent=2), encoding="utf-8")


def create_task_relation(parent_task_uid: str, child_task_uid: str, relation_type: str) -> None:
    """创建父子任务关系。"""

    relations = _load_relations()
    relations.append(
        {
            "relation_uid": f"rel-{uuid4().hex[:12]}",
            "parent_task_uid": parent_task_uid,
            "child_task_uid": child_task_uid,
            "relation_type": relation_type,
            "created_at": _now_iso(),
        }
    )
    _save_relations(relations)


def list_children(parent_task_uid: str) -> list[dict[str, str]]:
    """列出子任务。"""

    return [item for item in _load_relations() if item["parent_task_uid"] == parent_task_uid]


def list_parents(child_task_uid: str) -> list[dict[str, str]]:
    """列出父任务。"""

    return [item for item in _load_relations() if item["child_task_uid"] == child_task_uid]


def find_resume_candidates(parent_task_uid: str) -> list[dict[str, str]]:
    """查找可用于恢复父任务的子任务关系。"""

    from autodoengine.taskdb import task_store

    candidates: list[dict[str, str]] = []
    for relation in list_children(parent_task_uid):
        child = task_store.get_task(relation["child_task_uid"])
        if child.get("status") in {"completed", "cancelled"}:
            candidates.append(relation)
    return candidates

