"""运行时与事务注册表路径工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from autodoengine.taskdb.storage_paths import get_runtime_store_dirs, get_runtime_store_files
from autodoengine.utils.common.affair_sync import get_affair_registry_paths


def show_runtime_store_paths(base_dir: str | Path | None = None) -> Dict[str, str]:
    """返回运行时数据库目录与文件路径。

    Args:
        base_dir: 运行时根目录；为空时读取当前进程已初始化的运行时。

    Returns:
        目录与文件路径字典。
    """

    dirs = {key: str(value) for key, value in get_runtime_store_dirs(base_dir=base_dir).items()}
    files = {key: str(value) for key, value in get_runtime_store_files(base_dir=base_dir).items()}
    return {
        "runtime_base_dir": dirs["runtime_base_dir"],
        "taskdb_dir": dirs["taskdb"],
        "logdb_dir": dirs["logdb"],
        "decisiondb_dir": dirs["decisiondb"],
        "graph_registry_dir": dirs["graph_registry"],
        "tasks_file": files["tasks"],
        "task_relations_file": files["task_relations"],
        "task_steps_file": files["task_steps"],
        "snapshots_file": files["snapshots"],
        "runtime_events_file": files["runtime_events"],
        "decisions_file": files["decisions"],
        "graphs_file": files["graphs"],
        "types_file": files["types"],
    }


def show_affair_registry_paths(workspace_root: str | Path | None = None) -> Dict[str, str]:
    """返回事务管理路径。

    Args:
        workspace_root: 用户工作区根目录；为空时仅返回官方路径。

    Returns:
        路径字典。
    """

    workspace = Path(workspace_root).resolve() if workspace_root is not None else None
    return {key: str(value) for key, value in get_affair_registry_paths(workspace).items()}
