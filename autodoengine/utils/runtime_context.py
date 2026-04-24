"""运行时上下文（进程内）。

本模块用于在一次 `main.run()` 调度过程中，向下游工具函数传递“全局配置路径”等运行时信息。

设计目标：
- 避免把调度层（main.py）的概念渗透到每一个事务脚本里。
- 通过进程内的轻量上下文，让 LLM/密钥加载等通用能力能正确读取本次运行的全局 config。

注意：
- 该上下文仅在当前 Python 进程内有效，不会写入磁盘。
- 并行模式下，每个项目容器仍在同一进程不同线程中执行，因此这里使用线程局部变量隔离。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Optional


@dataclass
class RuntimeContext:
    """运行时上下文数据。

    Attributes:
        global_config_path: 当前调度过程使用的全局 config.json 绝对路径（可选）。
        current_affair_uid: 当前执行的事务 UID（可选）。
        current_affair_config_path: 当前执行事务的配置文件绝对路径（可选）。
    """

    global_config_path: Optional[Path] = None  # 全局 config.json 路径（绝对路径）
    current_affair_uid: Optional[str] = None
    current_affair_config_path: Optional[Path] = None


_tls = threading.local()


def set_runtime_context(
    *,
    global_config_path: str | Path | None = None,
    current_affair_uid: str | None = None,
    current_affair_config_path: str | Path | None = None,
) -> None:
    """设置线程内运行时上下文。

    Args:
        global_config_path: 全局 config.json 路径（可为 str/Path）。传 None 表示清空。
        current_affair_uid: 当前执行的事务 UID。
        current_affair_config_path: 当前执行事务的配置文件路径。
    """

    ctx = RuntimeContext(
        global_config_path=Path(global_config_path).resolve() if global_config_path else None,
        current_affair_uid=str(current_affair_uid).strip() if current_affair_uid else None,
        current_affair_config_path=Path(current_affair_config_path).resolve() if current_affair_config_path else None,
    )
    _tls.ctx = ctx


def get_runtime_context() -> RuntimeContext:
    """获取线程内运行时上下文。

    Returns:
        RuntimeContext 对象（若未设置则返回默认空上下文）。
    """

    ctx = getattr(_tls, "ctx", None)
    if isinstance(ctx, RuntimeContext):
        return ctx
    return RuntimeContext()


def get_global_config_path() -> Optional[Path]:
    """获取当前线程上下注入的全局 config.json 路径。

    Returns:
        Path 或 None。
    """

    return get_runtime_context().global_config_path


def get_current_affair_uid() -> Optional[str]:
    """获取当前线程上下注入的事务 UID。

    Returns:
        事务 UID 或 None。
    """

    return get_runtime_context().current_affair_uid


def get_current_affair_config_path() -> Optional[Path]:
    """获取当前线程上下注入的事务配置路径。

    Returns:
        事务配置文件路径或 None。
    """

    return get_runtime_context().current_affair_config_path

