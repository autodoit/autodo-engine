"""public capability 权限分级。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityPermission:
    """capability 权限配置。

    Args:
        exposure: 暴露级别，支持 `user`、`developer`、`internal`。
        side_effect: 副作用级别，支持 `none`、`write`。
        idempotent: 是否幂等。
    """

    exposure: str
    side_effect: str
    idempotent: bool


def assert_permission(permission: CapabilityPermission, *, allow_internal: bool) -> None:
    """校验调用权限。

    Args:
        permission: 权限配置。
        allow_internal: 是否允许 internal/developer 调用。

    Raises:
        PermissionError: 当前调用不允许时抛出。
    """

    if permission.exposure == "user":
        return
    if allow_internal:
        return
    raise PermissionError(f"能力权限不足：需要 {permission.exposure} 级别")
