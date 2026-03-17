"""事务数据库同步与运行时合并。

本模块实现官方库/用户库刷新，以及运行时优先级合并视图构建。
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping

from autodoengine.utils.common.affair_db import create_empty_registry, load_registry, now_iso, save_registry
from autodoengine.utils.common.affair_permissions import can_user_override, validate_user_record
from autodoengine.utils.common.affair_registry import build_records_from_root


SCHEMA_VERSION = "2026-03-12"


@dataclass(frozen=True)
class AffairSyncResult:
    """事务同步结果。

    Args:
        aok_db_path: 官方数据库路径。
        user_db_path: 用户数据库路径。
        records: 合并后的运行时记录列表。
        errors: 错误列表。
        warnings: 警告列表。
    """

    aok_db_path: Path
    user_db_path: Path
    records: List[Dict[str, Any]]
    errors: List[str]
    warnings: List[str]
    stats: Dict[str, int]


def default_aok_affairs_root() -> Path:
    """返回 AOK 内置事务目录。

    Returns:
        已安装 `autodo-kit` 包中的 `autodokit/affairs` 绝对路径。

    Examples:
        >>> default_aok_affairs_root().name
        'affairs'
    """

    spec = importlib.util.find_spec("autodokit")
    if spec is None:
        raise ModuleNotFoundError("未找到 autodokit 包。请先安装 autodo-kit。")

    package_roots = list(spec.submodule_search_locations or [])
    if package_roots:
        return (Path(package_roots[0]).resolve() / "affairs").resolve()

    if spec.origin is None:
        raise ModuleNotFoundError("无法定位 autodokit 包目录。")
    return (Path(spec.origin).resolve().parent / "affairs").resolve()


def default_aok_db_path() -> Path:
    """返回 AOK 官方事务数据库路径。

    Returns:
        引擎仓中的 `config/affair_registry.json` 绝对路径。

    Examples:
        >>> default_aok_db_path().name
        'affair_registry.json'
    """

    return (Path(__file__).resolve().parents[4] / "config" / "affair_registry.json").resolve()


def default_user_db_path(workspace_root: Path) -> Path:
    """返回用户事务数据库路径。

    Args:
        workspace_root: 用户工作区根目录。

    Returns:
        `<workspace_root>/.autodokit/affair_registry.json`。

    Examples:
        >>> from pathlib import Path
        >>> default_user_db_path(Path("demo")).name
        'affair_registry.json'
    """

    return (workspace_root / ".autodokit" / "affair_registry.json").resolve()


def default_user_affairs_root(workspace_root: Path) -> Path:
    """返回用户事务源码目录。

    Args:
        workspace_root: 用户工作区根目录。

    Returns:
        `<workspace_root>/.autodokit/affairs`。

    Examples:
        >>> from pathlib import Path
        >>> default_user_affairs_root(Path("demo")).name
        'affairs'
    """

    return (workspace_root / ".autodokit" / "affairs").resolve()


def get_affair_registry_paths(workspace_root: Path | None) -> Dict[str, Path]:
    """返回事务管理相关路径。

    Args:
        workspace_root: 用户工作区根目录；为空时仅返回官方路径。

    Returns:
        事务源码目录与事务数据库路径字典。
    """

    payload: Dict[str, Path] = {
        "aok_affairs_root": default_aok_affairs_root(),
        "aok_db_path": default_aok_db_path(),
    }
    if workspace_root is not None:
        resolved_workspace = workspace_root.resolve()
        payload["workspace_root"] = resolved_workspace
        payload["user_affairs_root"] = default_user_affairs_root(resolved_workspace)
        payload["user_db_path"] = default_user_db_path(resolved_workspace)
    return payload


def _build_stats(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """统计事务数据库记录数量。

    Args:
        records: 事务记录列表。

    Returns:
        统计信息字典。
    """

    return {
        "aok_graph": sum(1 for item in records if item.get("owner") == "aok" and item.get("domain") == "graph"),
        "aok_business": sum(1 for item in records if item.get("owner") == "aok" and item.get("domain") == "business"),
        "user_business": sum(1 for item in records if item.get("owner") == "user" and item.get("domain") == "business"),
        "invalid": sum(1 for item in records if str(item.get("status") or "") != "active"),
    }


def _build_db_payload(
    records: List[Dict[str, Any]],
    *,
    errors: List[str] | None = None,
    warnings: List[str] | None = None,
) -> Dict[str, Any]:
    """构建数据库写入结构。

    Args:
        records: 记录列表。

    Returns:
        数据库字典。

    Examples:
        >>> payload = _build_db_payload([])
        >>> payload["stats"]["invalid"]
        0
    """

    payload = create_empty_registry(schema_version=SCHEMA_VERSION)
    payload["generated_at"] = now_iso()
    payload["records"] = records
    payload["stats"] = _build_stats(records)
    payload["dirty_report"] = {
        "error_count": len(errors or []),
        "warning_count": len(warnings or []),
        "errors": list(errors or []),
        "warnings": list(warnings or []),
    }
    return payload


def _load_records_from_db(db_path: Path) -> List[Dict[str, Any]]:
    """读取数据库中的记录列表。

    Args:
        db_path: 数据库路径。

    Returns:
        记录列表。

    Examples:
        >>> from pathlib import Path
        >>> isinstance(_load_records_from_db(Path("not-exists.json")), list)
        True
    """

    db = load_registry(db_path, schema_version=SCHEMA_VERSION)
    records_raw = db.get("records")
    if not isinstance(records_raw, list):
        return []
    records: List[Dict[str, Any]] = []
    for item in records_raw:
        if isinstance(item, Mapping):
            records.append(dict(item))
    return records


def merge_runtime_records(*, aok_records: List[Dict[str, Any]], user_records: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str], List[str]]:
    """按优先级合并运行时事务记录。

    优先级：`user_business > aok_business > aok_graph`。

    Args:
        aok_records: 官方记录。
        user_records: 用户记录。

    Returns:
        三元组：合并记录、错误、警告。

    Examples:
        >>> records, errors, warnings = merge_runtime_records(aok_records=[], user_records=[])
        >>> records == [] and errors == []
        True
    """

    errors: List[str] = []
    warnings: List[str] = []

    aok_graph: Dict[str, Dict[str, Any]] = {}
    aok_business: Dict[str, Dict[str, Any]] = {}
    for item in aok_records:
        uid = str(item.get("affair_uid") or "").strip()
        if not uid:
            continue
        domain = str(item.get("domain") or "")
        if domain == "graph":
            aok_graph[uid] = item
        else:
            aok_business[uid] = item

    user_business: Dict[str, Dict[str, Any]] = {}
    for item in user_records:
        uid = str(item.get("affair_uid") or "").strip()
        if not uid:
            continue

        ok, reason = validate_user_record(item)
        if not ok:
            errors.append(f"用户事务[{uid}] 权限校验失败：{reason}")
            continue

        if uid in user_business:
            errors.append(f"用户层重复 affair_uid：{uid}")
            continue

        if uid in aok_graph:
            errors.append(f"用户事务[{uid}] 与官方 graph 事务冲突，拒绝注册")
            continue

        if uid in aok_business:
            allowed, forbid_reason = can_user_override(user_record=item, official_record=aok_business[uid])
            if not allowed:
                errors.append(f"用户事务[{uid}] 覆盖官方事务被拒绝：{forbid_reason}")
                continue
            warnings.append(f"用户事务[{uid}] 覆盖官方 business 事务")

        user_business[uid] = item

    runtime_records: List[Dict[str, Any]] = []
    runtime_records.extend(list(aok_graph.values()))
    runtime_records.extend(list(aok_business.values()))
    for uid, item in user_business.items():
        if uid in aok_business:
            runtime_records = [r for r in runtime_records if str(r.get("affair_uid") or "") != uid]
        runtime_records.append(item)

    return runtime_records, errors, warnings


def sync_affair_databases(
    *,
    workspace_root: Path | None,
    strict: bool = False,
    user_affairs_root: Path | None = None,
) -> AffairSyncResult:
    """同步事务数据库并构建运行时视图。

    Args:
        workspace_root: 用户工作区根目录；为空时仅加载官方库。
        strict: 严格模式下遇到错误抛异常。
        user_affairs_root: 用户事务目录，可选覆盖默认路径。

    Returns:
        同步结果对象。

    Raises:
        ValueError: 严格模式下存在错误时抛出。

    Examples:
        >>> result = sync_affair_databases(workspace_root=None, strict=False)
        >>> isinstance(result.records, list)
        True
    """

    errors: List[str] = []
    warnings: List[str] = []

    aok_root = default_aok_affairs_root()
    aok_db_path = default_aok_db_path()

    aok_records, aok_errors, aok_warnings = build_records_from_root(root=aok_root, owner="aok")
    errors.extend(aok_errors)
    warnings.extend(aok_warnings)

    if aok_records:
        save_registry(aok_db_path, _build_db_payload(aok_records, errors=aok_errors, warnings=aok_warnings))
    elif not aok_db_path.exists():
        save_registry(aok_db_path, _build_db_payload([], errors=[], warnings=[]))

    resolved_aok_records = _load_records_from_db(aok_db_path)

    if workspace_root is None:
        runtime_records = resolved_aok_records
        result = AffairSyncResult(
            aok_db_path=aok_db_path,
            user_db_path=Path(""),
            records=runtime_records,
            errors=errors,
            warnings=warnings,
            stats=_build_stats(runtime_records),
        )
        if strict and errors:
            raise ValueError("事务同步失败：\n" + "\n".join(errors))
        return result

    workspace = workspace_root.resolve()
    user_db_path = default_user_db_path(workspace)
    user_root = (user_affairs_root or default_user_affairs_root(workspace)).resolve()

    user_records, user_errors, user_warnings = build_records_from_root(root=user_root, owner="user")
    errors.extend(user_errors)
    warnings.extend(user_warnings)

    save_registry(user_db_path, _build_db_payload(user_records, errors=user_errors, warnings=user_warnings))
    resolved_user_records = _load_records_from_db(user_db_path)

    runtime_records, merge_errors, merge_warnings = merge_runtime_records(
        aok_records=resolved_aok_records,
        user_records=resolved_user_records,
    )
    errors.extend(merge_errors)
    warnings.extend(merge_warnings)

    if strict and errors:
        raise ValueError("事务同步失败：\n" + "\n".join(errors))

    return AffairSyncResult(
        aok_db_path=aok_db_path,
        user_db_path=user_db_path,
        records=runtime_records,
        errors=errors,
        warnings=warnings,
        stats=_build_stats(runtime_records),
    )


def build_runtime_registry(
    *,
    workspace_root: Path | None,
    strict: bool = False,
    user_affairs_root: Path | None = None,
) -> Dict[str, Dict[str, Any]]:
    """构建运行时事务查询视图。

    Args:
        workspace_root: 用户工作区根目录。
        strict: 严格模式开关。
        user_affairs_root: 用户事务目录，可选。

    Returns:
        `affair_uid -> 事务记录` 映射。

    Raises:
        ValueError: 严格模式下同步失败时抛出。

    Examples:
        >>> registry = build_runtime_registry(workspace_root=None, strict=False)
        >>> isinstance(registry, dict)
        True
    """

    result = sync_affair_databases(
        workspace_root=workspace_root,
        strict=strict,
        user_affairs_root=user_affairs_root,
    )
    registry: Dict[str, Dict[str, Any]] = {}
    for record in result.records:
        uid = str(record.get("affair_uid") or "").strip()
        if not uid:
            continue
        registry[uid] = dict(record)
    return registry

