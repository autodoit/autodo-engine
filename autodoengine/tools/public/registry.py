"""public capability 注册表。"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping

from autodoengine.tools.public.permissions import CapabilityPermission


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """capability 定义。

    Args:
        capability_id: 能力标识。
        summary: 能力摘要。
        module: 实现模块。
        callable_name: 实现函数名。
        exposure: 暴露级别。
        side_effect: 副作用级别。
        idempotent: 是否幂等。
        input_schema_path: 输入 schema 路径。
        output_schema_path: 输出 schema 路径。
    """

    capability_id: str
    summary: str
    module: str
    callable_name: str
    exposure: str
    side_effect: str
    idempotent: bool
    input_schema_path: Path
    output_schema_path: Path

    @property
    def permission(self) -> CapabilityPermission:
        """返回权限配置。

        Returns:
            权限对象。
        """

        return CapabilityPermission(
            exposure=self.exposure,
            side_effect=self.side_effect,
            idempotent=self.idempotent,
        )


def _manifest_path() -> Path:
    """返回 manifest 文件路径。

    Returns:
        manifest 绝对路径。
    """

    return (Path(__file__).resolve().parent / "manifest" / "public_tools_manifest.json").resolve()


def _load_json(path: Path) -> Dict[str, Any]:
    """读取 JSON 文件。

    Args:
        path: JSON 文件路径。

    Returns:
        JSON 对象。
    """

    return json.loads(path.read_text(encoding="utf-8"))


def _schema_path(file_name: str) -> Path:
    """返回 schema 路径。

    Args:
        file_name: schema 文件名。

    Returns:
        schema 绝对路径。
    """

    return (Path(__file__).resolve().parent / "schemas" / file_name).resolve()


def load_capability_manifest() -> List[CapabilityDefinition]:
    """加载 capability manifest。

    Returns:
        capability 定义列表。
    """

    raw = _load_json(_manifest_path())
    items = raw.get("capabilities") if isinstance(raw, Mapping) else []
    definitions: List[CapabilityDefinition] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        definitions.append(
            CapabilityDefinition(
                capability_id=str(item.get("capability_id") or "").strip(),
                summary=str(item.get("summary") or "").strip(),
                module=str(item.get("module") or "").strip(),
                callable_name=str(item.get("callable") or "").strip(),
                exposure=str(item.get("exposure") or "user").strip(),
                side_effect=str(item.get("side_effect") or "none").strip(),
                idempotent=bool(item.get("idempotent", True)),
                input_schema_path=_schema_path(str(item.get("input_schema") or "")),
                output_schema_path=_schema_path(str(item.get("output_schema") or "")),
            )
        )
    return definitions


def list_capabilities(*, include_internal: bool = False) -> List[Dict[str, Any]]:
    """列出 capability 摘要。

    Args:
        include_internal: 是否包含非 user 能力。

    Returns:
        摘要列表。
    """

    rows: List[Dict[str, Any]] = []
    for item in load_capability_manifest():
        if item.exposure != "user" and not include_internal:
            continue
        rows.append(
            {
                "capability_id": item.capability_id,
                "summary": item.summary,
                "exposure": item.exposure,
                "side_effect": item.side_effect,
                "idempotent": item.idempotent,
            }
        )
    return rows


def get_capability(capability_id: str) -> CapabilityDefinition:
    """按 ID 获取 capability 定义。

    Args:
        capability_id: 能力标识。

    Returns:
        capability 定义。

    Raises:
        KeyError: 能力不存在时抛出。
    """

    target = str(capability_id or "").strip()
    for item in load_capability_manifest():
        if item.capability_id == target:
            return item
    raise KeyError(f"capability 不存在：{target}")


def resolve_callable(definition: CapabilityDefinition) -> Any:
    """解析 capability 对应函数。

    Args:
        definition: capability 定义。

    Returns:
        可调用对象。
    """

    module = importlib.import_module(definition.module)
    return getattr(module, definition.callable_name)


def lint_public_manifest() -> Dict[str, Any]:
    """校验 manifest 与实现的一致性。

    Returns:
        lint 摘要字典。
    """

    errors: List[str] = []
    warnings: List[str] = []
    seen: set[str] = set()

    for item in load_capability_manifest():
        if not item.capability_id:
            errors.append("存在空 capability_id")
            continue
        if item.capability_id in seen:
            errors.append(f"重复 capability_id：{item.capability_id}")
        seen.add(item.capability_id)
        if not item.input_schema_path.exists():
            errors.append(f"输入 schema 不存在：{item.input_schema_path}")
        if not item.output_schema_path.exists():
            errors.append(f"输出 schema 不存在：{item.output_schema_path}")
        try:
            callable_obj = resolve_callable(item)
            if not callable(callable_obj):
                errors.append(f"能力不可调用：{item.capability_id}")
        except Exception as exc:
            errors.append(f"能力加载失败：{item.capability_id}：{exc}")

    return {
        "passed": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "capability_count": len(seen),
    }
