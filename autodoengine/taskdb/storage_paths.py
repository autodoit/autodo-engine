"""运行时存储路径管理。"""

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
    return {
        "runtime_base_dir": base,
        "taskdb": base / "taskdb",
        "logdb": base / "logdb",
        "decisiondb": base / "decisiondb",
        "graph_registry": base / "graph_registry",
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
    return {
        "tasks": taskdb / "tasks.json",
        "task_relations": taskdb / "task_relations.json",
        "task_steps": taskdb / "task_steps.json",
        "snapshots": taskdb / "snapshots.json",
        "runtime_events": logdb / "runtime_events.jsonl",
        "decisions": decisiondb / "decisions.json",
        "graphs": graph_registry / "graphs.json",
        "types": graph_registry / "types.json",
    }


def resolve_store_file(*, kind: str, name: str) -> Path:
    """解析存储文件绝对路径。"""

    base = get_runtime_base_dir()
    folder = {
        "taskdb": base / "taskdb",
        "logdb": base / "logdb",
        "decisiondb": base / "decisiondb",
        "graph_registry": base / "graph_registry",
    }[kind]
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name
