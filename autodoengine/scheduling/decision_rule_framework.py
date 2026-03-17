"""v4 决策部门框架解析与判定工具。"""

from __future__ import annotations

from typing import Any

from autodoengine.core.enums import ResultCode
from autodoengine.core.types import NodeContext

_DEFAULT_CONDITION = "abnormal_upgrade"
_DEFAULT_MEMBERS = ["pa", "human"]
_VALID_CONDITIONS = {"abnormal_upgrade", "always"}
_VALID_MEMBERS = {"pa", "human", "ta", "na", "aa"}
_VALID_ROUTE_MODES = {"direct", "decision"}


def _normalize_condition(raw_value: Any) -> str:
    """规范化介入条件。

    Args:
        raw_value: 原始配置值。

    Returns:
        str: 合法介入条件。

    Raises:
        None.

    Examples:
        >>> _normalize_condition("always")
        'always'
    """

    value = str(raw_value or _DEFAULT_CONDITION).strip().lower()
    if value not in _VALID_CONDITIONS:
        return _DEFAULT_CONDITION
    return value


def _normalize_members(raw_value: Any) -> list[str]:
    """规范化决策部门成员列表。

    Args:
        raw_value: 原始配置值，支持字符串或列表。

    Returns:
        list[str]: 去重后的合法成员列表。

    Raises:
        None.

    Examples:
        >>> _normalize_members(["pa", "human", "pa"])
        ['pa', 'human']
    """

    if isinstance(raw_value, str):
        source = [raw_value]
    elif isinstance(raw_value, list):
        source = raw_value
    else:
        source = list(_DEFAULT_MEMBERS)

    normalized: list[str] = []
    for item in source:
        member = str(item or "").strip().lower()
        if member in _VALID_MEMBERS and member not in normalized:
            normalized.append(member)

    if not normalized:
        return list(_DEFAULT_MEMBERS)
    return normalized


def _extract_department_config(container: dict[str, Any]) -> dict[str, Any]:
    """提取决策部门配置片段。

    Args:
        container: 图级或节点级策略字典。

    Returns:
        dict[str, Any]: 决策部门配置。

    Raises:
        None.

    Examples:
        >>> _extract_department_config({"decision_department": {"intervention_condition": "always"}})
        {'intervention_condition': 'always'}
    """

    payload = container.get("decision_department") if isinstance(container, dict) else None
    return dict(payload) if isinstance(payload, dict) else {}


def resolve_decision_framework(*, graph_policies: dict[str, Any], node_context: NodeContext) -> dict[str, Any]:
    """解析当前节点的决策部门配置。

    Args:
        graph_policies: 流程图级策略。
        node_context: 当前节点上下文。

    Returns:
        dict[str, Any]: 生效后的决策部门配置。

    Raises:
        None.

    Examples:
        >>> from autodoengine.core.types import NodeContext
        >>> node = NodeContext(node_uid="n1", node_type="process", affair_uid=None, risk_level="normal", policies={})
        >>> output = resolve_decision_framework(graph_policies={}, node_context=node)
        >>> output["route_mode"]
        'direct'
    """

    route_mode_raw = node_context.policies.get("route_mode") or node_context.policies.get("routing_mode")
    route_mode = str(route_mode_raw or "direct").strip().lower()
    if route_mode not in _VALID_ROUTE_MODES:
        route_mode = "direct"

    graph_rule = _extract_department_config(graph_policies)
    node_rule = _extract_department_config(node_context.policies)

    graph_condition = _normalize_condition(graph_rule.get("intervention_condition"))
    graph_members = _normalize_members(graph_rule.get("members"))

    node_condition = _normalize_condition(node_rule.get("intervention_condition")) if node_rule else graph_condition
    node_members = _normalize_members(node_rule.get("members")) if node_rule else graph_members

    if route_mode == "direct":
        condition = _DEFAULT_CONDITION
        members = graph_members
    else:
        condition = node_condition
        members = node_members

    return {
        "route_mode": route_mode,
        "intervention_condition": condition,
        "members": members,
        "decision_mode": str(node_rule.get("decision_mode") or graph_rule.get("decision_mode") or "JOINT").upper(),
    }


def should_invoke_decision_department(*, result_code: ResultCode, framework: dict[str, Any]) -> bool:
    """判断是否需要进入决策部门。

    Args:
        result_code: 事务回执结果码。
        framework: 生效后的决策规则框架。

    Returns:
        bool: 是否触发决策部门。

    Raises:
        None.

    Examples:
        >>> should_invoke_decision_department(result_code=ResultCode.PASS, framework={"intervention_condition": "abnormal_upgrade"})
        False
    """

    condition = str(framework.get("intervention_condition") or _DEFAULT_CONDITION)
    if condition == "always":
        return True
    return result_code in {ResultCode.RETRY, ResultCode.BACKTRACK, ResultCode.BLOCKED}

