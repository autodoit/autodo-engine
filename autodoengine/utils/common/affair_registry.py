"""事务扫描与记录构建。

本模块负责扫描事务清单、校验最小字段并构造标准化记录。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from autodoengine.utils.common.affair_db import now_iso
from autodoengine.utils.common.affair_permissions import validate_domain_owner


PASS_MODE_SET = {"config_path", "config_dict"}


def scan_affair_manifests(root: Path) -> List[Path]:
    """扫描目录下所有事务清单。

    Args:
        root: 事务根目录。

    Returns:
        `affair.json` 路径列表（排序后）。

    Examples:
        >>> from pathlib import Path
        >>> isinstance(scan_affair_manifests(Path(".")), list)
        True
    """

    if not root.exists():
        return []
    return sorted(root.glob("*/affair.json"))


def read_manifest(manifest_path: Path) -> Dict[str, Any]:
    """读取单个事务清单。

    Args:
        manifest_path: 清单路径。

    Returns:
        清单字典。

    Raises:
        ValueError: 文件不可读或结构非法时抛出。

    Examples:
        >>> from pathlib import Path
        >>> _ = read_manifest(Path("not_exists_affair.json"))
    """

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"读取事务清单失败：{manifest_path}：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"事务清单必须为 JSON 对象：{manifest_path}")
    return data


def validate_manifest(item: Mapping[str, Any], *, affair_dir: Path) -> Tuple[List[str], List[str]]:
    """校验事务清单字段。

    Args:
        item: 清单字典。
        affair_dir: 事务目录。

    Returns:
        (errors, warnings) 二元组。

    Examples:
        >>> errs, warns = validate_manifest({"name": "x"}, affair_dir=Path("x"))
        >>> isinstance(errs, list) and isinstance(warns, list)
        True
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
    if pass_mode not in PASS_MODE_SET:
        errors.append(f"{affair_dir}: runner.pass_mode 仅支持 config_path/config_dict")

    docs = item.get("docs") if isinstance(item.get("docs"), Mapping) else {}
    md_path_raw = str(docs.get("md_path") or "").strip()
    if not md_path_raw:
        warnings.append(f"{affair_dir}: docs.md_path 为空")

    py_path = (affair_dir / "affair.py").resolve()
    if not py_path.exists():
        errors.append(f"{affair_dir}: 缺少 affair.py")

    return errors, warnings


def infer_domain(item: Mapping[str, Any], *, affair_name: str) -> str:
    """推断事务域。

    Args:
        item: 清单字典。
        affair_name: 事务名。

    Returns:
        `graph` 或 `business`。

    Examples:
        >>> infer_domain({}, affair_name="图节点_start")
        'graph'
    """

    domain_raw = str(item.get("domain") or "").strip().lower()
    if domain_raw in {"graph", "business"}:
        return domain_raw

    node = item.get("node") if isinstance(item.get("node"), Mapping) else {}
    if bool(node.get("is_graph", False)):
        return "graph"
    if affair_name.startswith("图节点_"):
        return "graph"
    return "business"


def build_record(
    *,
    manifest: Mapping[str, Any],
    manifest_path: Path,
    owner: str,
) -> Dict[str, Any]:
    """根据清单构造标准事务记录。

    Args:
        manifest: 清单字典。
        manifest_path: 清单路径。
        owner: 所有者（`aok` 或 `user`）。

    Returns:
        标准记录字典。

    Raises:
        ValueError: 关键字段缺失或非法时抛出。

    Examples:
        >>> p = Path("a/affair.json")
        >>> m = {"name": "a", "runner": {"module": "m", "callable": "c", "pass_mode": "config_path"}}
        >>> rec = build_record(manifest=m, manifest_path=p, owner="aok")
        >>> rec["affair_uid"] == "a"
        True
    """

    name = str(manifest.get("name") or "").strip()
    if not name:
        raise ValueError(f"{manifest_path}: 缺少 name")

    runner = manifest.get("runner") if isinstance(manifest.get("runner"), Mapping) else {}
    module = str(runner.get("module") or "").strip()
    callable_name = str(runner.get("callable") or "").strip() or "execute"
    pass_mode = str(runner.get("pass_mode") or "").strip() or "config_path"
    if pass_mode not in PASS_MODE_SET:
        raise ValueError(f"{manifest_path}: runner.pass_mode 非法：{pass_mode}")

    docs = manifest.get("docs") if isinstance(manifest.get("docs"), Mapping) else {}
    docs_md_path = str(docs.get("md_path") or "").strip()

    domain = infer_domain(manifest, affair_name=name)
    ok, reason = validate_domain_owner(domain=domain, owner=owner)
    if not ok:
        raise ValueError(f"{manifest_path}: {reason}")

    raw_manifest = json.dumps(dict(manifest), ensure_ascii=False, sort_keys=True)
    manifest_hash = hashlib.sha256(raw_manifest.encode("utf-8")).hexdigest()

    record: Dict[str, Any] = {
        "affair_uid": name,
        "name": name,
        "version": str(manifest.get("version") or "0.0.0"),
        "domain": domain,
        "owner": owner,
        "source": str((manifest_path.parent / "affair.py").resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "runner": {
            "module": module,
            "callable": callable_name,
            "pass_mode": pass_mode,
            "kwargs": dict(runner.get("kwargs") or {}) if isinstance(runner.get("kwargs"), Mapping) else {},
        },
        "docs": {
            "md_path": docs_md_path,
        },
        "status": "active",
        "manifest_hash": manifest_hash,
        "updated_at": now_iso(),
        "manifest": dict(manifest),
    }
    return record


def build_records_from_root(*, root: Path, owner: str) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """扫描并构建事务记录集合。

    Args:
        root: 事务根目录。
        owner: 所有者。

    Returns:
        三元组：记录列表、错误列表、警告列表。

    Examples:
        >>> from pathlib import Path
        >>> records, errors, warnings = build_records_from_root(root=Path("."), owner="aok")
        >>> isinstance(records, list)
        True
    """

    records: List[Dict[str, Any]] = []
    errors: List[str] = []
    warnings: List[str] = []
    seen_uids: set[str] = set()

    for manifest_path in scan_affair_manifests(root):
        affair_dir = manifest_path.parent
        try:
            manifest = read_manifest(manifest_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        manifest_errors, manifest_warnings = validate_manifest(manifest, affair_dir=affair_dir)
        errors.extend(manifest_errors)
        warnings.extend(manifest_warnings)
        if manifest_errors:
            continue

        try:
            record = build_record(manifest=manifest, manifest_path=manifest_path, owner=owner)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        affair_uid = str(record["affair_uid"])
        if affair_uid in seen_uids:
            errors.append(f"同层重复 affair_uid：{affair_uid}（{manifest_path}）")
            continue
        seen_uids.add(affair_uid)
        records.append(record)

    return records, errors, warnings

