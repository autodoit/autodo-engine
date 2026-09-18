"""项目配置归一化：把宿主写出的项目级 config 收敛为单一英文内部契约视图。

设计基准 O5：主入口曾经直读英文键（`api.py` 读 `runtime.workflow_graph_path`），
而宿主按中文主契约书写（`运行时.流程图路径`），导致漏读、误报"缺字段"。

本模块提供**唯一**的归一化入口：读入 config.json 后先过一次
`normalize_project_config`，之后所有 reader 只消费规范视图，禁止再裸读某个语言键。
"""

from __future__ import annotations

from typing import Any, Mapping

from autodoengine.utils.config_contract_utils import normalize_to_legacy_contract


def normalize_project_config(raw: Any) -> dict[str, Any]:
    """把项目级配置归一为英文内部契约视图。

    宿主既可用中文主契约（`运行时.流程图路径`）书写，也可用英文旧契约
    （`runtime.workflow_graph_path`）书写；归一后两者收敛为同一份英文视图，
    reader 只需按英文键读取，不再依赖某一种语言书写。英文键原样保留，
    中文键与中文取值按 `config_contract_utils` 的映射表翻译为英文。

    Args:
        raw: 从 config.json 读出的原始对象（预期为映射）。

    Returns:
        归一后的英文内部契约字典；输入非映射时返回空字典。

    Examples:
        >>> cfg = normalize_project_config({"运行时": {"流程图路径": "a.json"}})
        >>> cfg["runtime"]["workflow_graph_path"]
        'a.json'
    """

    if not isinstance(raw, Mapping):
        return {}
    normalized = normalize_to_legacy_contract(dict(raw))
    return normalized if isinstance(normalized, dict) else {}


__all__ = ["normalize_project_config"]
