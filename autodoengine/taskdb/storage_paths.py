"""运行时存储路径管理（统一落到 workspace/database SQLite）。"""

from __future__ import annotations

from pathlib import Path
from typing import overload


_RUNTIME_BASE_DIR: Path | None = None


def set_runtime_base_dir(base_dir: str) -> None:
    """设置运行时存储根目录。"""

    global _RUNTIME_BASE_DIR
    _RUNTIME_BASE_DIR = Path(base_dir).resolve()


def get_runtime_base_dir() -> Path:
    """获取运行时存储根目录。"""

    if _RUNTIME_BASE_DIR is None:
        raise RuntimeError("运行时存储未初始化，请先调用 bootstrap_runtime_storage")
    return _RUNTIME_BASE_DIR


def get_runtime_store_dirs(base_dir: str | Path | None = None) -> dict[str, Path]:
    """返回运行时各数据库目录。

    Args:
        base_dir: 可选运行时根目录；为空时读取当前进程已初始化的运行时根目录。

    Returns:
        以数据库类别名为键、目录绝对路径为值的字典。
    """

    base = Path(base_dir).resolve() if base_dir is not None else get_runtime_base_dir()
    workspace_root = _resolve_workspace_root(base)
    database_root = workspace_root / "database"
    return {
        "runtime_base_dir": base,
        "workspace_root": workspace_root,
        "database_root": database_root,
        "taskdb": database_root / "tasks",
        "logdb": database_root / "logs",
        "decisiondb": database_root / "decision",
        "graph_registry": database_root / "runtime_registry",
    }


def get_runtime_store_files(base_dir: str | Path | None = None) -> dict[str, Path]:
    """返回运行时已约定的数据库文件路径。

    Args:
        base_dir: 可选运行时根目录；为空时读取当前进程已初始化的运行时根目录。

    Returns:
        以逻辑文件名为键、文件绝对路径为值的字典。
    """

    folders = get_runtime_store_dirs(base_dir=base_dir)
    taskdb = folders["taskdb"]
    logdb = folders["logdb"]
    decisiondb = folders["decisiondb"]
    graph_registry = folders["graph_registry"]
    tasks_db = taskdb / "tasks.db"
    log_db = logdb / "aok_log.db"
    decision_db = decisiondb / "decision.db"
    graph_registry_db = graph_registry / "graph_registry.db"
    return {
        "tasks": tasks_db,
        "task_relations": tasks_db,
        "task_steps": tasks_db,
        "snapshots": tasks_db,
        "runtime_events": log_db,
        "decisions": decision_db,
        "graphs": graph_registry_db,
        "types": graph_registry_db,
        "tasks_db": tasks_db,
        "log_db": log_db,
        "decision_db": decision_db,
        "graph_registry_db": graph_registry_db,
    }


def _resolve_workspace_root(base: Path) -> Path:
    """根据 runtime base 反推 workspace 根目录。"""

    candidates: list[Path] = [base, *base.parents]
    for item in candidates:
        if (item / "database").exists() and (item / "config").exists():
            return item

    for item in candidates:
        workspace = item / "workspace"
        if (workspace / "database").exists() and (workspace / "config").exists():
            return workspace.resolve()

    # 回退：若没有现成 workspace，使用 base 本身。
    return base.resolve()


def resolve_store_file(*, kind: str, name: str) -> Path:
    """解析存储文件绝对路径。"""

    dirs = get_runtime_store_dirs(get_runtime_base_dir())
    folder = {
        "taskdb": dirs["taskdb"],
        "logdb": dirs["logdb"],
        "decisiondb": dirs["decisiondb"],
        "graph_registry": dirs["graph_registry"],
    }[kind]
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name
