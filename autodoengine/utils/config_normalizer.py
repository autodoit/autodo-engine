"""契约归一化：把宿主写出的 config / 注册表 / 流程图收敛为单一英文内部契约视图。

设计基准 O5：主入口曾经直读英文键（`api.py` 读 `runtime.workflow_graph_path`），
而宿主按中文主契约书写（`运行时.流程图路径`），导致漏读、误报"缺字段"。

宿主写三份文件都可能用中文主契约：项目 `config.json`、事务入口注册表、流程图 JSON。
本模块提供**唯一**的归一化入口：任何一份读进来后先过一次 `normalize_to_legacy_view`，
之后所有 reader 只消费规范视图，禁止再裸读某个语言键。
"""

from __future__ import annotations

from typing import Any, Mapping

from autodoengine.utils.config_contract_utils import normalize_to_legacy_contract


def normalize_to_legacy_view(raw: Any) -> dict[str, Any]:
    """把宿主书写的映射归一为英文内部契约视图。

    适用于项目 config、事务入口注册表与流程图 JSON：宿主既可用中文主契约
    （`运行时.流程图路径`、`记录[].节点编码`、`节点[].节点唯一标识`）书写，
    也可用英文旧契约书写；归一后两者收敛为同一份英文视图，reader 只需按英文键读取。
    英文键原样保留，中文键与中文取值按 `config_contract_utils` 的映射表翻译为英文。

    Args:
        raw: 从 JSON 读出的原始对象（预期为映射）。

    Returns:
        归一后的英文内部契约字典；输入非映射时返回空字典。

    Examples:
        >>> cfg = normalize_to_legacy_view({"运行时": {"流程图路径": "a.json"}})
        >>> cfg["runtime"]["workflow_graph_path"]
        'a.json'
    """

    if not isinstance(raw, Mapping):
        return {}
    normalized = normalize_to_legacy_contract(dict(raw))
    return normalized if isinstance(normalized, dict) else {}


__all__ = ["normalize_to_legacy_view"]
