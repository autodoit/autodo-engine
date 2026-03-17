"""运行时存储初始化。"""

from __future__ import annotations

from pathlib import Path

from .storage_paths import set_runtime_base_dir


def bootstrap_taskdb(base_dir: str) -> None:
    """初始化 taskdb 存储。"""

    target = Path(base_dir).resolve() / "taskdb"
    target.mkdir(parents=True, exist_ok=True)


def bootstrap_logdb(base_dir: str) -> None:
    """初始化 logdb 存储。"""

    target = Path(base_dir).resolve() / "logdb"
    target.mkdir(parents=True, exist_ok=True)


def bootstrap_decisiondb(base_dir: str) -> None:
    """初始化 decisiondb 存储。"""

    target = Path(base_dir).resolve() / "decisiondb"
    target.mkdir(parents=True, exist_ok=True)


def bootstrap_graph_registry(base_dir: str) -> None:
    """初始化 graph_registry 存储。"""

    target = Path(base_dir).resolve() / "graph_registry"
    target.mkdir(parents=True, exist_ok=True)


def bootstrap_runtime_storage(base_dir: str) -> None:
    """初始化完整运行时目录结构。"""

    root = Path(base_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    bootstrap_taskdb(str(root))
    bootstrap_logdb(str(root))
    bootstrap_decisiondb(str(root))
    bootstrap_graph_registry(str(root))
    set_runtime_base_dir(str(root))
