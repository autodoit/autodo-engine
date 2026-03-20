"""事务注册中心工具。

本模块负责扫描 `autodokit/affairs/*/affair.json`，并提供统一的事务元数据校验、
索引构建、执行入口解析与文档路径查询能力。
官方事务内容由 `autodo-kit` 提供，当前模块只负责引擎侧解析与运行时合并。
"""

from __future__ import annotations

import difflib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from autodoengine.utils.common.affair_permissions import validate_domain_owner
from autodoengine.utils.common.affair_sync import build_runtime_registry, default_aok_affairs_root, sync_affair_databases


@dataclass(frozen=True)
class AffairLintResult:
    """事务校验结果。

    Args:
        passed: 是否通过校验。
        errors: 错误列表。
        warnings: 警告列表。
        scanned_count: 扫描到的事务数量。
    """

    passed: bool
    errors: List[str]
    warnings: List[str]
    scanned_count: int


def _default_affairs_root() -> Path:
    """返回默认事务目录根路径。

    Returns:
        默认官方事务目录的绝对路径。
    """

    return default_aok_affairs_root()


def scan_affairs(root: Path | None = None) -> List[Path]:
    """扫描事务清单文件。

    Args:
        root: 事务根目录，默认为 `autodokit/affairs`。

    Returns:
        所有 `affair.json` 路径（按路径排序）。
    """

    affairs_root = (root or _default_affairs_root()).resolve()
    if not affairs_root.exists():
        return []
    return sorted(affairs_root.glob("*/affair.json"))


def _read_manifest(manifest_path: Path) -> Dict[str, Any]:
    """读取单个事务元数据。

    Args:
        manifest_path: `affair.json` 路径。

    Returns:
        反序列化后的字典。

    Raises:
        ValueError: 读取失败或 JSON 非法时抛出。
    """

    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        raise ValueError(f"读取事务清单失败：{manifest_path}：{exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"事务清单必须为 JSON 对象：{manifest_path}")
    return data


def validate_affair_manifest(item: Mapping[str, Any], affair_dir: Path) -> Tuple[List[str], List[str]]:
    """校验事务元数据结构。

    Args:
        item: `affair.json` 字典。
        affair_dir: 事务目录。

    Returns:
        (errors, warnings) 二元组。
    """

    errors: List[str] = []
    warnings: List[str] = []

    dir_name = affair_dir.name
    name = str(item.get("name") or "").strip()
    if not name:
        errors.append(f"{affair_dir}: 缺少 name")
    elif name != dir_name:
        errors.append(f"{affair_dir}: name 与目录名不一致（name={name}, dir={dir_name}）")

    runner = item.get("runner") if isinstance(item.get("runner"), Mapping) else {}
    module = str(runner.get("module") or "").strip()
    callable_name = str(runner.get("callable") or "").strip()
    pass_mode = str(runner.get("pass_mode") or "").strip()
    if not module:
        errors.append(f"{affair_dir}: runner.module 不能为空")
    if not callable_name:
        errors.append(f"{affair_dir}: runner.callable 不能为空")
    if pass_mode not in {"config_path", "config_dict"}:
        errors.append(f"{affair_dir}: runner.pass_mode 仅支持 config_path/config_dict")

    domain = str(item.get("domain") or "").strip().lower()
    owner = str(item.get("owner") or "").strip().lower()
    if not domain:
        errors.append(f"{affair_dir}: domain 不能为空（graph/business）")
    if not owner:
        errors.append(f"{affair_dir}: owner 不能为空（aok/user）")
    if domain and owner:
        ok, reason = validate_domain_owner(domain=domain, owner=owner)
        if not ok:
            errors.append(f"{affair_dir}: {reason}")

    docs = item.get("docs") if isinstance(item.get("docs"), Mapping) else {}
    md_path_raw = str(docs.get("md_path") or "").strip()
    if not md_path_raw:
        warnings.append(f"{affair_dir}: docs.md_path 为空")
    else:
        repo_root = affair_dir.parents[2]
        md_path = _normalize_docs_path(md_path_raw, repo_root=repo_root)
        if not md_path.exists():
            errors.append(f"{affair_dir}: docs.md_path 不存在：{md_path}")

    py_path = (affair_dir / "affair.py").resolve()
    if not py_path.exists():
        errors.append(f"{affair_dir}: 缺少 affair.py")

    node = item.get("node")
    if node is not None:
        if not isinstance(node, Mapping):
            errors.append(f"{affair_dir}: node 字段必须是对象")
        else:
            node_type = str(node.get("node_type") or "").strip()
            if not node_type:
                errors.append(f"{affair_dir}: node.node_type 不能为空")

            affair_type = str(node.get("affair_type") or "").strip()
            if not affair_type:
                errors.append(f"{affair_dir}: node.affair_type 不能为空")

            content_kind = str(node.get("content_kind") or "affair").strip() or "affair"
            if content_kind != "affair":
                errors.append(f"{affair_dir}: node.content_kind 当前仅支持 affair")

            allow_multi_input_ports = node.get("allow_multi_input_ports") or []
            if not isinstance(allow_multi_input_ports, list):
                errors.append(f"{affair_dir}: node.allow_multi_input_ports 必须是列表")

            for field_name in ("inputs", "outputs", "payload_defaults", "config"):
                value = node.get(field_name)
                if value is not None and not isinstance(value, Mapping):
                    errors.append(f"{affair_dir}: node.{field_name} 必须是对象")

    return errors, warnings


def _build_registry_from_root(root: Path | None = None, *, strict: bool = False) -> Dict[str, Dict[str, Any]]:
    """构建事务注册表。

    Args:
        root: 事务根目录。
        strict: 为真时，遇到校验错误直接抛出异常。

    Returns:
        `name -> manifest` 映射。

    Raises:
        ValueError: strict 模式下存在校验错误。
    """

    registry: Dict[str, Dict[str, Any]] = {}
    all_errors: List[str] = []

    for manifest_path in scan_affairs(root):
        affair_dir = manifest_path.parent
        try:
            manifest = _read_manifest(manifest_path)
        except ValueError as exc:
            all_errors.append(str(exc))
            continue

        errors, _ = validate_affair_manifest(manifest, affair_dir)
        if errors:
            all_errors.extend(errors)
            continue

        name = str(manifest.get("name") or "").strip()
        if not name:
            all_errors.append(f"{manifest_path}: 缺少 name")
            continue

        if name in registry:
            all_errors.append(f"重复事务 name：{name}（{manifest_path}）")
            continue

        registry[name] = dict(manifest)

    if strict and all_errors:
        raise ValueError("事务注册表构建失败：\n" + "\n".join(all_errors))

    return registry


def build_runtime_registry_view(
    *,
    workspace_root: Path | None = None,
    strict: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """构建运行时事务视图（记录级）。

    Args:
        workspace_root: 用户工作区根目录。
        strict: 严格模式开关。

    Returns:
        `affair_uid -> 事务记录` 映射。

    Raises:
        ValueError: 严格模式下同步失败时抛出。
    """

    return build_runtime_registry(workspace_root=workspace_root, strict=strict)


def build_registry(
    root: Path | None = None,
    *,
    strict: bool = False,
    workspace_root: Path | None = None,
) -> Dict[str, Dict[str, Any]]:
    """构建事务注册表。

    当传入 `root` 时，行为与历史版本一致：仅扫描指定目录。
    当 `root` 为空时，启用事务管理系统的数据库同步与运行时合并视图。

    Args:
        root: 事务根目录；传入时仅扫描该目录。
        strict: 为真时，遇到校验错误直接抛出异常。
        workspace_root: 用户工作区根目录；仅在 `root` 为空时生效。

    Returns:
        `affair_uid -> manifest` 映射。

    Raises:
        ValueError: strict 模式下存在校验错误。
    """

    if root is not None:
        return _build_registry_from_root(root=root, strict=strict)

    sync_result = sync_affair_databases(workspace_root=workspace_root, strict=strict)
    registry: Dict[str, Dict[str, Any]] = {}

    for record in sync_result.records:
        affair_uid = str(record.get("affair_uid") or "").strip()
        if not affair_uid:
            continue
        manifest = record.get("manifest") if isinstance(record.get("manifest"), Mapping) else {}
        if isinstance(manifest, Mapping) and manifest:
            registry[affair_uid] = dict(manifest)
            continue

        registry[affair_uid] = {
            "name": record.get("name") or affair_uid,
            "domain": record.get("domain") or "business",
            "owner": record.get("owner") or "aok",
            "docs": dict(record.get("docs") or {}) if isinstance(record.get("docs"), Mapping) else {},
            "runner": dict(record.get("runner") or {}) if isinstance(record.get("runner"), Mapping) else {},
        }

    return registry


def build_module_alias_index(registry: Mapping[str, Mapping[str, Any]]) -> Dict[str, str]:
    """构建模块别名索引。

    Args:
        registry: 事务注册表。

    Returns:
        `module_alias -> affair_name` 映射。
    """

    index: Dict[str, str] = {}
    for affair_name, manifest in registry.items():
        runner = manifest.get("runner") if isinstance(manifest.get("runner"), Mapping) else {}
        module = str(runner.get("module") or "").strip()
        if module:
            index[module] = affair_name
            normalized_module = _normalize_runner_module(module)
            index[normalized_module] = affair_name

        legacy = manifest.get("legacy") if isinstance(manifest.get("legacy"), Mapping) else {}
        aliases = legacy.get("module_aliases") if isinstance(legacy.get("module_aliases"), list) else []
        for alias in aliases:
            alias_str = str(alias or "").strip()
            if alias_str:
                index[alias_str] = affair_name
                normalized_alias = _normalize_runner_module(alias_str)
                index[normalized_alias] = affair_name
    return index


def resolve_runner(affair_name: str, registry: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """解析事务执行入口。

    Args:
        affair_name: 事务名。
        registry: 事务注册表。

    Returns:
        包含 `module/callable/pass_mode` 的 runner 字典。

    Raises:
        KeyError: 事务不存在时抛出。
        ValueError: runner 结构不完整时抛出。
    """

    key = str(affair_name or "").strip()
    if key not in registry:
        candidates = difflib.get_close_matches(key, list(registry.keys()), n=5, cutoff=0.45)
        hint = f"；候选：{', '.join(candidates)}" if candidates else ""
        raise KeyError(f"事务不存在：{key}{hint}")

    manifest = registry[key]
    runner = manifest.get("runner") if isinstance(manifest.get("runner"), Mapping) else {}
    module = _normalize_runner_module(str(runner.get("module") or "").strip())
    source_py_path = str(runner.get("source_py_path") or manifest.get("source_py_path") or "").strip()
    callable_name = str(runner.get("callable") or "execute").strip() or "execute"
    pass_mode = str(runner.get("pass_mode") or "config_path").strip() or "config_path"
    if not module and not source_py_path:
        raise ValueError(f"事务[{key}] 缺少 runner.module 或 runner.source_py_path")
    if pass_mode not in {"config_path", "config_dict"}:
        raise ValueError(f"事务[{key}] runner.pass_mode 非法：{pass_mode}")
    return {
        "module": module,
        "source_py_path": source_py_path,
        "callable": callable_name,
        "pass_mode": pass_mode,
        "kwargs": dict(runner.get("kwargs") or {}) if isinstance(runner.get("kwargs"), Mapping) else {},
    }


def get_affair_docs(affair_name: str, registry: Mapping[str, Mapping[str, Any]]) -> Path:
    """获取事务文档路径。

    Args:
        affair_name: 事务名。
        registry: 事务注册表。

    Returns:
        事务文档绝对路径。

    Raises:
        KeyError: 事务不存在。
        ValueError: 文档路径不存在。
    """

    key = str(affair_name or "").strip()
    if key not in registry:
        raise KeyError(f"事务不存在：{key}")

    docs = registry[key].get("docs") if isinstance(registry[key].get("docs"), Mapping) else {}
    md_path_raw = str(docs.get("md_path") or "").strip()
    if not md_path_raw:
        raise ValueError(f"事务[{key}] 缺少 docs.md_path")

    repo_root = _default_affairs_root().parents[1]
    md_path = _normalize_docs_path(md_path_raw, repo_root=repo_root)

    if not md_path.exists():
        raise ValueError(f"事务[{key}] 文档不存在：{md_path}")
    return md_path


def lint_affairs(root: Path | None = None, *, check_import: bool = True) -> AffairLintResult:
    """校验事务目录结构与 runner 可导入性。

    Args:
        root: 事务根目录。
        check_import: 是否检查模块可导入与 callable 存在。

    Returns:
        校验结果对象。
    """

    errors: List[str] = []
    warnings: List[str] = []
    scanned = 0

    registry = build_registry(root=root, strict=False)
    scanned = len(registry)

    manifest_paths = scan_affairs(root)
    for manifest_path in manifest_paths:
        affair_dir = manifest_path.parent
        try:
            manifest = _read_manifest(manifest_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        manifest_errors, manifest_warnings = validate_affair_manifest(manifest, affair_dir)
        errors.extend(manifest_errors)
        warnings.extend(manifest_warnings)

    if check_import:
        for affair_name in sorted(registry.keys()):
            try:
                runner = resolve_runner(affair_name, registry)
                module_path = str(runner["module"])
                callable_name = str(runner["callable"])
                module = importlib.import_module(module_path)
                callable_obj = getattr(module, callable_name, None)
                if not callable(callable_obj):
                    errors.append(f"事务[{affair_name}] runner 不可调用：{module_path}:{callable_name}")
            except Exception as exc:
                errors.append(f"事务[{affair_name}] runner 校验失败：{exc}")

    return AffairLintResult(
        passed=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
        scanned_count=scanned,
    )


def _normalize_docs_path(md_path_raw: str, *, repo_root: Path) -> Path:
    """将事务文档路径规范化到当前仓库布局。"""

    raw = str(md_path_raw or "").strip()
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()

    normalized = raw.replace("\\", "/")
    if normalized.startswith("autodoengine/affairs/"):
        normalized = normalized.replace("autodoengine/affairs/", "autodokit/affairs/", 1)
    candidates = [normalized]

    for candidate in candidates:
        resolved = (repo_root / Path(candidate)).resolve()
        if resolved.exists():
            return resolved
    return (repo_root / Path(candidates[0])).resolve()


def _normalize_runner_module(module_path: str) -> str:
    """将事务 runner 模块路径归一化到 `autodo-kit` 包路径。"""

    module = str(module_path or "").strip()
    if module.startswith("autodoengine.affairs."):
        return module.replace("autodoengine.affairs.", "autodokit.affairs.", 1)
    return module


