"""public capability facade。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from autodoengine.tools.public.audit import write_audit_record
from autodoengine.tools.public.permissions import assert_permission
from autodoengine.tools.public.protocol import build_error_response, build_success_response
from autodoengine.tools.public.registry import get_capability, list_capabilities as _list_capabilities, resolve_callable


def _validate_type(value: Any, expected_type: str) -> bool:
    """校验基础类型。

    Args:
        value: 待校验值。
        expected_type: 期望类型。

    Returns:
        是否匹配。
    """

    mapping = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "integer": int,
        "number": (int, float),
    }
    target = mapping.get(expected_type)
    if target is None:
        return True
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, target)


def _validate_schema(value: Any, schema: Mapping[str, Any], *, label: str) -> list[str]:
    """按轻量 schema 校验数据。

    Args:
        value: 待校验值。
        schema: schema 字典。
        label: 错误标签。

    Returns:
        错误消息列表。
    """

    errors: list[str] = []
    schema_type = str(schema.get("type") or "").strip()
    if schema_type and not _validate_type(value, schema_type):
        errors.append(f"{label} 类型错误，期望 {schema_type}")
        return errors

    if schema_type == "object":
        properties = schema.get("properties") if isinstance(schema.get("properties"), Mapping) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        additional_properties = bool(schema.get("additionalProperties", True))
        value_dict = value if isinstance(value, dict) else {}
        for field in required:
            if field not in value_dict:
                errors.append(f"{label}.{field} 缺失")
        for key, item in value_dict.items():
            if key not in properties:
                if not additional_properties:
                    errors.append(f"{label}.{key} 不允许出现")
                continue
            if isinstance(properties.get(key), Mapping):
                errors.extend(_validate_schema(item, properties[key], label=f"{label}.{key}"))

    if schema_type == "array":
        item_schema = schema.get("items") if isinstance(schema.get("items"), Mapping) else {}
        for index, item in enumerate(value if isinstance(value, list) else []):
            errors.extend(_validate_schema(item, item_schema, label=f"{label}[{index}]"))

    return errors


def _load_schema(path: Path) -> Dict[str, Any]:
    """读取 schema 文件。

    Args:
        path: schema 文件路径。

    Returns:
        schema 字典。
    """

    import json

    return json.loads(path.read_text(encoding="utf-8"))


def list_capabilities(*, include_internal: bool = False) -> list[dict[str, Any]]:
    """列出 capability 摘要。

    Args:
        include_internal: 是否包含非 user 能力。

    Returns:
        capability 摘要列表。
    """

    return _list_capabilities(include_internal=include_internal)


def invoke_capability(
    capability_id: str,
    *,
    payload: Dict[str, Any] | None = None,
    caller_context: Dict[str, Any] | None = None,
    allow_internal: bool = False,
    workspace_root: str | Path | None = None,
) -> Dict[str, Any]:
    """统一执行 capability。

    Args:
        capability_id: 能力标识。
        payload: 输入参数字典。
        caller_context: 调用上下文。
        allow_internal: 是否允许 internal/developer 能力。
        workspace_root: 工作区根目录，用于审计落盘。

    Returns:
        统一协议字典。
    """

    target = str(capability_id or "").strip()
    normalized_payload = dict(payload or {})
    context = dict(caller_context or {})
    context.setdefault("caller_source", "autodoengine.tools.public.facade")

    audit_seed = {
        "capability_id": target,
        "payload": normalized_payload,
        "caller_context": context,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        definition = get_capability(target)
        assert_permission(definition.permission, allow_internal=allow_internal)
        schema = _load_schema(definition.input_schema_path)
        payload_errors = _validate_schema(normalized_payload, schema, label="payload")
        if payload_errors:
            audit_seed["status"] = "error"
            audit_seed["errors"] = payload_errors
            audit_path = write_audit_record(audit_seed, workspace_root=workspace_root)
            return build_error_response(
                target,
                code="invalid_payload",
                message="输入参数校验失败",
                audit_path=str(audit_path),
                details={"errors": payload_errors},
                metadata={"exposure": definition.exposure},
            ).to_dict()

        callable_obj = resolve_callable(definition)
        result = callable_obj(**normalized_payload)
        result_payload = result if isinstance(result, dict) else {"result": result}
        output_schema = _load_schema(definition.output_schema_path)
        output_errors = _validate_schema(result_payload, output_schema, label="result")
        warnings = output_errors if output_errors else []

        audit_seed["status"] = "success"
        audit_seed["result"] = result_payload
        audit_seed["warnings"] = warnings
        audit_path = write_audit_record(audit_seed, workspace_root=workspace_root)
        return build_success_response(
            target,
            data=result_payload,
            audit_path=str(audit_path),
            warnings=warnings,
            metadata={
                "exposure": definition.exposure,
                "side_effect": definition.side_effect,
                "idempotent": definition.idempotent,
            },
        ).to_dict()
    except Exception as exc:
        audit_seed["status"] = "error"
        audit_seed["exception"] = str(exc)
        audit_path = write_audit_record(audit_seed, workspace_root=workspace_root)
        return build_error_response(
            target,
            code="execution_failed",
            message=str(exc),
            audit_path=str(audit_path),
            details={"exception_type": exc.__class__.__name__},
        ).to_dict()
