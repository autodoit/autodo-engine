"""模板事务基类。

该模块用于提供“事务模板化”的统一生命周期：
- 前置检查：`pre_check_can_start`
- 业务执行：`run_business`
- 完成检查：`post_check_completed`
- 健康检查：`post_check_healthy`

设计目标：
- 让图节点事务与业务事务共享统一骨架；
- 将公共治理/日志逻辑集中在基类，减少重复代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

from autodoengine.utils.path_tools import load_json_or_py


class TemplateAffairBase(ABC):
    """模板事务基类。

    Args:
        affair_name: 事务名称（用于日志与报表标识）。

    Examples:
        >>> class DemoAffair(TemplateAffairBase):
        ...     def run_business(self, *, config, workspace_root):
        ...         return []
        >>> DemoAffair(affair_name="demo")
    """

    def __init__(self, *, affair_name: str) -> None:
        """初始化模板事务。

        Args:
            affair_name: 事务名称。
        """

        self.affair_name = str(affair_name).strip() or self.__class__.__name__

    def load_config(self, config_path: Path | str) -> Dict[str, Any]:
        """读取事务配置。

        Args:
            config_path: 调度器传入的配置路径。

        Returns:
            配置字典。若配置不是字典，则返回空字典。
        """

        data = load_json_or_py(Path(config_path))
        if not isinstance(data, dict):
            return {}
        return data

    def pre_check_can_start(self, *, config: Dict[str, Any], workspace_root: Path | None) -> None:
        """前置可开始检查钩子。

        Args:
            config: 事务配置。
            workspace_root: 工作区根目录。

        Returns:
            None。

        Raises:
            RuntimeError: 子类可在不满足启动条件时抛出。
        """

        return None

    @abstractmethod
    def run_business(self, *, config: Dict[str, Any], workspace_root: Path | None) -> List[Path]:
        """执行核心业务逻辑。

        Args:
            config: 事务配置。
            workspace_root: 工作区根目录。

        Returns:
            产出文件路径列表。
        """

    def post_check_completed(
        self,
        *,
        config: Dict[str, Any],
        workspace_root: Path | None,
        outputs: List[Path],
    ) -> None:
        """完成性检查钩子。

        Args:
            config: 事务配置。
            workspace_root: 工作区根目录。
            outputs: 业务执行产出路径。

        Returns:
            None。

        Raises:
            RuntimeError: 子类可在完成性不满足时抛出。
        """

        return None

    def post_check_healthy(
        self,
        *,
        config: Dict[str, Any],
        workspace_root: Path | None,
        outputs: List[Path],
        error: Exception | None,
    ) -> None:
        """健康性检查钩子。

        Args:
            config: 事务配置。
            workspace_root: 工作区根目录。
            outputs: 业务执行产出路径。
            error: 执行阶段捕获的异常。

        Returns:
            None。
        """

        return None

    def execute(self, config_path: Path | str, workspace_root: Path | None = None) -> List[Path]:
        """模板事务标准执行入口。

        Args:
            config_path: 调度器传入配置路径。
            workspace_root: 工作区根目录。

        Returns:
            产出文件路径列表。

        Raises:
            Exception: 抛出业务执行或检查阶段产生的异常。

        Examples:
            >>> class DemoAffair(TemplateAffairBase):
            ...     def run_business(self, *, config, workspace_root):
            ...         return []
            >>> DemoAffair(affair_name="demo").execute("demo.json")  # doctest: +SKIP
        """

        config = self.load_config(config_path)
        self.pre_check_can_start(config=config, workspace_root=workspace_root)

        outputs: List[Path] = []
        run_error: Exception | None = None
        try:
            outputs = self.run_business(config=config, workspace_root=workspace_root)
            self.post_check_completed(
                config=config,
                workspace_root=workspace_root,
                outputs=outputs,
            )
            return outputs
        except Exception as exc:  # noqa: BLE001
            run_error = exc
            raise
        finally:
            self.post_check_healthy(
                config=config,
                workspace_root=workspace_root,
                outputs=outputs,
                error=run_error,
            )

