"""事务运行与导入工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def run_affair_tool(
    affair_uid: str,
    *,
    config: Dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    workspace_root: str | Path | None = None,
    strict: bool = False,
    runner_kwargs: Dict[str, Any] | None = None,
) -> List[str]:
    """运行事务并返回产物路径。

    Args:
        affair_uid: 事务 UID。
        config: 字典配置。
        config_path: 配置文件路径。
        workspace_root: 工作区根目录。
        strict: 严格模式。
        runner_kwargs: 额外 runner 参数。

    Returns:
        产物路径字符串列表。
    """

    from autodoengine import api

    outputs = api.run_affair(
        affair_uid,
        config=config,
        config_path=config_path,
        workspace_root=workspace_root,
        strict=strict,
        runner_kwargs=runner_kwargs,
    )
    return [str(item) for item in outputs]


def import_user_affair_tool(
    source_py_path: str | Path,
    workspace_root: str | Path,
    source_params_json_path: str | Path | None = None,
    source_doc_md_path: str | Path | None = None,
    affair_name: str | None = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """导入用户功能程序为事务三件套。

    Args:
        source_py_path: 功能程序文件路径。
        workspace_root: 用户工作区根目录。
        source_params_json_path: 参数模板 JSON 路径。
        source_doc_md_path: 说明文档 MD 路径。
        affair_name: 事务名称。
        strict: 严格模式。

    Returns:
        导入摘要。
    """

    from autodoengine import api

    return api.import_user_affair(
        source_py_path=Path(source_py_path).resolve(),
        workspace_root=Path(workspace_root).resolve(),
        source_params_json_path=Path(source_params_json_path).resolve() if source_params_json_path is not None else None,
        source_doc_md_path=Path(source_doc_md_path).resolve() if source_doc_md_path is not None else None,
        affair_name=affair_name,
        strict=strict,
    )
