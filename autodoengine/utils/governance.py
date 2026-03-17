"""治理协议与判定工具。

本模块用于承载 P8 阶段的“管理官治理协议”最小实现，目标是：
- 统一流程官 / 节点官配置结构；
- 提供稳定的判定输入输出协议；
- 解耦具体模型供应商，默认以规则引擎兜底。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable


_ALLOWED_CHECKS = {"can_start", "completed", "healthy"}
_ALLOWED_FAIL_MODES = {"block", "warn", "retry"}


@dataclass(frozen=True, slots=True)
class GovernanceBudgetConfig:
    """治理预算配置。

    Args:
        max_calls: 最大调用次数（0 表示不限制）。
        timeout_seconds: 单次判定超时时间（秒）。
        max_cost: 本次流程允许的最大预算（保留字段）。

    Returns:
        None。

    Examples:
        >>> GovernanceBudgetConfig(max_calls=10, timeout_seconds=15)
    """

    max_calls: int = 0
    timeout_seconds: int = 15
    max_cost: float = 0.0


@dataclass(frozen=True, slots=True)
class GovernanceRoleConfig:
    """治理角色配置（流程官 / 节点官）。

    Args:
        role: 角色名称，例如 `process_officer` 或 `node_officer`。
        enabled: 是否启用治理。
        model_profile: 模型类型配置（语言大/小、视觉大/小等）。
        api_key_path: API Key 文件路径（可为空）。
        checks: 启用的判定项集合。
        fail_mode: 判定失败策略（`block` / `warn` / `retry`）。
        budget: 预算配置。
        node_type_whitelist: 节点官白名单节点类型（仅节点官使用）。

    Returns:
        None。

    Examples:
        >>> cfg = GovernanceRoleConfig(role="process_officer", enabled=True)
        >>> cfg.role
        'process_officer'
    """

    role: str
    enabled: bool = False
    model_profile: str = "language-small"
    api_key_path: str = ""
    checks: tuple[str, ...] = ("can_start", "completed", "healthy")
    fail_mode: str = "warn"
    budget: GovernanceBudgetConfig = field(default_factory=GovernanceBudgetConfig)
    node_type_whitelist: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GovernanceDecision:
    """治理判定结果协议。

    Args:
        role: 判定角色。
        check: 判定类型。
        passed: 是否通过。
        reason: 判定原因。
        error_code: 错误码（通过时可为空）。
        source: 判定来源（rule_engine / llm_stub / disabled）。
        fail_mode: 当前判定对应的失败策略。

    Returns:
        None。

    Examples:
        >>> result = GovernanceDecision(role="node_officer", check="can_start", passed=True, reason="ok")
        >>> result.passed
        True
    """

    role: str
    check: str
    passed: bool
    reason: str
    error_code: str = ""
    source: str = "rule_engine"
    fail_mode: str = "warn"


def _normalize_checks(raw: Iterable[str] | None) -> tuple[str, ...]:
    """规范化治理检查项集合。

    Args:
        raw: 原始检查项集合。

    Returns:
        合法检查项元组。
    """

    if raw is None:
        return ("can_start", "completed", "healthy")

    out: list[str] = []
    for item in raw:
        key = str(item).strip().lower()
        if key in _ALLOWED_CHECKS and key not in out:
            out.append(key)
    if not out:
        return ("can_start", "completed", "healthy")
    return tuple(out)


def build_governance_role_config(
    raw: Dict[str, Any] | None,
    *,
    role: str,
) -> GovernanceRoleConfig:
    """从原始字典构建治理角色配置。

    Args:
        raw: 原始配置对象。
        role: 角色名称。

    Returns:
        规范化后的治理角色配置。

    Raises:
        ValueError: 角色名为空时抛出。

    Examples:
        >>> build_governance_role_config({"enabled": True}, role="process_officer").enabled
        True
    """

    role_name = str(role).strip()
    if not role_name:
        raise ValueError("role 不能为空")

    data = raw if isinstance(raw, dict) else {}
    budget_raw = data.get("budget") if isinstance(data.get("budget"), dict) else {}

    fail_mode = str(data.get("fail_mode") or "warn").strip().lower()
    if fail_mode not in _ALLOWED_FAIL_MODES:
        fail_mode = "warn"

    whitelist_raw = data.get("node_type_whitelist")
    whitelist: list[str] = []
    if isinstance(whitelist_raw, list):
        whitelist = [str(x).strip().lower() for x in whitelist_raw if str(x).strip()]
    elif role_name == "node_officer":
        whitelist = ["if", "container"]

    return GovernanceRoleConfig(
        role=role_name,
        enabled=bool(data.get("enabled", False)),
        model_profile=str(data.get("model_profile") or "language-small").strip() or "language-small",
        api_key_path=str(data.get("api_key_path") or "").strip(),
        checks=_normalize_checks(data.get("checks") if isinstance(data.get("checks"), list) else None),
        fail_mode=fail_mode,
        budget=GovernanceBudgetConfig(
            max_calls=max(0, int(budget_raw.get("max_calls") or 0)),
            timeout_seconds=max(1, int(budget_raw.get("timeout_seconds") or 15)),
            max_cost=float(budget_raw.get("max_cost") or 0.0),
        ),
        node_type_whitelist=tuple(whitelist),
    )


def run_governance_check(
    *,
    profile: GovernanceRoleConfig,
    check: str,
    context: Dict[str, Any] | None = None,
) -> GovernanceDecision:
    """执行治理判定。

    说明：
    - 本实现默认使用规则引擎作为稳定基线；
    - 未来可在不改调用方的前提下替换为真实 LLM 判定。

    Args:
        profile: 治理角色配置。
        check: 判定类型（`can_start`/`completed`/`healthy`）。
        context: 判定上下文。

    Returns:
        治理判定结果。

    Examples:
        >>> profile = build_governance_role_config({"enabled": True}, role="process_officer")
        >>> run_governance_check(profile=profile, check="can_start", context={"allow_start": True}).passed
        True
    """

    check_key = str(check).strip().lower()
    ctx = context if isinstance(context, dict) else {}

    if check_key not in _ALLOWED_CHECKS:
        return GovernanceDecision(
            role=profile.role,
            check=check_key,
            passed=True,
            reason="未知检查项，按通过处理",
            source="rule_engine",
            fail_mode=profile.fail_mode,
        )

    if not profile.enabled:
        return GovernanceDecision(
            role=profile.role,
            check=check_key,
            passed=True,
            reason="治理未启用",
            source="disabled",
            fail_mode=profile.fail_mode,
        )

    if check_key not in profile.checks:
        return GovernanceDecision(
            role=profile.role,
            check=check_key,
            passed=True,
            reason="该检查未启用",
            source="rule_engine",
            fail_mode=profile.fail_mode,
        )

    if check_key == "can_start":
        allow_start = bool(ctx.get("allow_start", True))
        force_block = bool(ctx.get("force_block", False))
        passed = allow_start and not force_block
        return GovernanceDecision(
            role=profile.role,
            check=check_key,
            passed=passed,
            reason="允许开始" if passed else "治理阻止开始",
            error_code="" if passed else "GOV_CAN_START_REJECTED",
            source="rule_engine",
            fail_mode=profile.fail_mode,
        )

    if check_key == "completed":
        passed = bool(ctx.get("success", False))
        return GovernanceDecision(
            role=profile.role,
            check=check_key,
            passed=passed,
            reason="执行完成" if passed else "执行未完成",
            error_code="" if passed else "GOV_NOT_COMPLETED",
            source="rule_engine",
            fail_mode=profile.fail_mode,
        )

    has_error = bool(ctx.get("has_error", False))
    passed = not has_error
    return GovernanceDecision(
        role=profile.role,
        check=check_key,
        passed=passed,
        reason="运行健康" if passed else "运行异常",
        error_code="" if passed else "GOV_NOT_HEALTHY",
        source="rule_engine",
        fail_mode=profile.fail_mode,
    )
