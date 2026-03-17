"""事务权限与冲突规则。

本模块负责 owner/domain 合法性约束及运行时冲突策略。
"""

from __future__ import annotations

from typing import Any, Mapping, Tuple

_ALLOWED_DOMAIN = {"graph", "business"}
_ALLOWED_OWNER = {"aok", "user"}


def validate_domain_owner(*, domain: str, owner: str) -> Tuple[bool, str | None]:
    """校验域与所有者字段是否合法。

    Args:
        domain: 事务域。
        owner: 所有者。

    Returns:
        二元组：是否合法、错误信息。

    Examples:
        >>> validate_domain_owner(domain="business", owner="aok")[0]
        True
    """

    if domain not in _ALLOWED_DOMAIN:
        return False, f"domain 非法：{domain}"
    if owner not in _ALLOWED_OWNER:
        return False, f"owner 非法：{owner}"
    return True, None


def validate_user_record(record: Mapping[str, Any]) -> Tuple[bool, str | None]:
    """校验用户事务记录权限边界。

    Args:
        record: 事务记录。

    Returns:
        二元组：是否合法、错误信息。

    Examples:
        >>> validate_user_record({"owner": "user", "domain": "business"})[0]
        True
    """

    owner = str(record.get("owner") or "")
    domain = str(record.get("domain") or "")
    if owner != "user":
        return False, "用户事务 owner 必须为 user"
    if domain != "business":
        return False, "用户事务仅允许 business 域"
    return True, None


def can_user_override(*, user_record: Mapping[str, Any], official_record: Mapping[str, Any]) -> Tuple[bool, str | None]:
    """判断用户事务是否允许覆盖官方事务。

    Args:
        user_record: 用户侧记录。
        official_record: 官方侧记录。

    Returns:
        二元组：是否允许覆盖、原因（禁止时）。

    Examples:
        >>> can_user_override(user_record={"domain": "business"}, official_record={"domain": "business"})[0]
        True
    """

    official_domain = str(official_record.get("domain") or "")
    if official_domain == "graph":
        return False, "用户事务不允许覆盖官方 graph 域事务"
    user_domain = str(user_record.get("domain") or "")
    if user_domain != "business":
        return False, "用户事务仅允许 business 域"
    return True, None
