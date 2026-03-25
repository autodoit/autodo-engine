"""public capability 统一返回协议。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class CapabilityErrorDetail:
    """capability 错误明细。

    Args:
        code: 错误码。
        message: 错误描述。
        details: 补充细节。
    """

    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CapabilityResponse:
    """capability 统一响应。

    Args:
        status: 执行状态。
        code: 响应码。
        capability_id: capability 标识。
        data: 响应数据。
        audit_path: 审计文件路径。
        warnings: 告警列表。
        errors: 错误明细列表。
        metadata: 元数据字典。
    """

    status: str
    code: str
    capability_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    audit_path: str = ""
    warnings: List[str] = field(default_factory=list)
    errors: List[CapabilityErrorDetail] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。

        Returns:
            JSON 兼容字典。
        """

        payload = asdict(self)
        payload["errors"] = [asdict(item) for item in self.errors]
        return payload


def build_success_response(
    capability_id: str,
    *,
    data: Dict[str, Any],
    audit_path: str,
    warnings: List[str] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> CapabilityResponse:
    """构造成功响应。

    Args:
        capability_id: capability 标识。
        data: 输出数据。
        audit_path: 审计文件路径。
        warnings: 告警列表。
        metadata: 元数据。

    Returns:
        成功响应对象。
    """

    return CapabilityResponse(
        status="success",
        code="ok",
        capability_id=capability_id,
        data=data,
        audit_path=audit_path,
        warnings=list(warnings or []),
        metadata=dict(metadata or {}),
    )


def build_error_response(
    capability_id: str,
    *,
    code: str,
    message: str,
    audit_path: str,
    details: Dict[str, Any] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> CapabilityResponse:
    """构造失败响应。

    Args:
        capability_id: capability 标识。
        code: 响应码。
        message: 错误描述。
        audit_path: 审计文件路径。
        details: 细节字典。
        metadata: 元数据。

    Returns:
        失败响应对象。
    """

    return CapabilityResponse(
        status="error",
        code=code,
        capability_id=capability_id,
        audit_path=audit_path,
        errors=[CapabilityErrorDetail(code=code, message=message, details=dict(details or {}))],
        metadata=dict(metadata or {}),
    )
