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


def _load_aok_metadata_overrides() -> Dict[str, Dict[str, Any]]:
    """读取官方事务元数据覆盖表。

    Returns:
        `affair_name -> metadata` 映射。
    """

    path = (Path(__file__).resolve().parents[3] / "config" / "affair_metadata_overrides.json").resolve()
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(data, Mapping):
        return {}

    output: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(value, Mapping):
            output[str(key)] = dict(value)
    return output


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

    manifests: List[Path] = []
    for affair_dir in sorted(root.iterdir()):
        if not affair_dir.is_dir():
            continue
        if any((affair_dir / name).exists() for name in ("affair.py", "affair.json", "affair.md")):
            manifests.append((affair_dir / "affair.json").resolve())
    return manifests


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

    if not manifest_path.exists():
        raise ValueError(f"读取事务清单失败：{manifest_path}：文件不存在")

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

    py_path = (affair_dir / "affair.py").resolve()
    json_path = (affair_dir / "affair.json").resolve()
    md_path = (affair_dir / "affair.md").resolve()
    if not py_path.exists():
        errors.append(f"{affair_dir}: 缺少 affair.py")
    if not json_path.exists():
        errors.append(f"{affair_dir}: 缺少 affair.json")
    if not md_path.exists():
        warnings.append(f"{affair_dir}: 缺少 affair.md（建议补充事务说明文档）")

    runner = item.get("runner") if isinstance(item.get("runner"), Mapping) else {}
    if runner:
        pass_mode = str(runner.get("pass_mode") or "").strip() or "config_path"
        if pass_mode not in PASS_MODE_SET:
            errors.append(f"{affair_dir}: runner.pass_mode 仅支持 config_path/config_dict")

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


def _looks_like_legacy_manifest(item: Mapping[str, Any]) -> bool:
    """判断是否为旧版事务清单结构。

    Args:
        item: `affair.json` 字典。

    Returns:
        是否包含旧版元数据字段。
    """

    legacy_keys = {"name", "runner", "domain", "owner", "docs", "node", "legacy"}
    return any(key in item for key in legacy_keys)


def _default_runner_module(*, owner: str, folder_name: str) -> str:
    """根据事务目录推断默认 runner 模块路径。

    Args:
        owner: 事务所有者。
        folder_name: 事务目录名。

    Returns:
        默认模块路径字符串。
    """

    if owner == "aok":
        return f"autodokit.affairs.{folder_name}.affair"
    return ""


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

    affair_dir = manifest_path.parent.resolve()
    folder_name = affair_dir.name
    is_legacy = _looks_like_legacy_manifest(manifest)

    display_name = str(manifest.get("name") or "").strip() if is_legacy else folder_name
    if not display_name:
        display_name = folder_name

    affair_uid = str(manifest.get("affair_uid") or "").strip() if is_legacy else ""
    if not affair_uid:
        affair_uid = display_name

    aok_overrides = _load_aok_metadata_overrides() if owner == "aok" else {}
    override_raw = aok_overrides.get(display_name)
    override = dict(override_raw) if isinstance(override_raw, Mapping) else {}

    runner = manifest.get("runner") if isinstance(manifest.get("runner"), Mapping) else {}
    if isinstance(override.get("runner"), Mapping):
        runner = dict(override.get("runner") or {})
    module = str(runner.get("module") or "").strip()
    if not module:
        module = _default_runner_module(owner=owner, folder_name=folder_name)
    callable_name = str(runner.get("callable") or "").strip() or "execute"
    pass_mode = str(runner.get("pass_mode") or "").strip() or "config_path"
    if pass_mode not in PASS_MODE_SET:
        raise ValueError(f"{manifest_path}: runner.pass_mode 非法：{pass_mode}")

    docs = manifest.get("docs") if isinstance(manifest.get("docs"), Mapping) else {}
    if isinstance(override.get("docs"), Mapping):
        docs = dict(override.get("docs") or {})
    docs_md_path = str(docs.get("md_path") or "").strip()
    if not docs_md_path:
        docs_md_path = str((affair_dir / "affair.md").resolve())

    override_domain = str(override.get("domain") or "").strip().lower()
    if override_domain in {"graph", "business"}:
        domain = override_domain
    else:
        domain = infer_domain(manifest if is_legacy else {}, affair_name=display_name)
    ok, reason = validate_domain_owner(domain=domain, owner=owner)
    if not ok:
        raise ValueError(f"{manifest_path}: {reason}")

    raw_manifest = json.dumps(dict(manifest), ensure_ascii=False, sort_keys=True)
    manifest_hash = hashlib.sha256(raw_manifest.encode("utf-8")).hexdigest()
    now_text = now_iso()

    node_meta = manifest.get("node") if isinstance(manifest.get("node"), Mapping) else {}
    node_template = {
        "node_type": str(node_meta.get("node_type") or ("process" if domain == "business" else "graph")).strip(),
        "affair_type": str(node_meta.get("affair_type") or affair_uid).strip(),
        "config": dict(node_meta.get("config") or {}) if isinstance(node_meta.get("config"), Mapping) else {},
        "inputs": dict(node_meta.get("inputs") or {}) if isinstance(node_meta.get("inputs"), Mapping) else {},
        "outputs": dict(node_meta.get("outputs") or {}) if isinstance(node_meta.get("outputs"), Mapping) else {},
        "payload_defaults": dict(node_meta.get("payload_defaults") or {})
        if isinstance(node_meta.get("payload_defaults"), Mapping)
        else {},
        "flags": {
            "allow_multi_input_ports": list(node_meta.get("allow_multi_input_ports") or [])
            if isinstance(node_meta.get("allow_multi_input_ports"), list)
            else [],
            "is_leaf": bool(node_meta.get("is_leaf", True)),
            "is_business": bool(node_meta.get("is_business", domain == "business")),
            "is_graph": bool(node_meta.get("is_graph", domain == "graph")),
        },
    }
    if isinstance(override.get("node_template"), Mapping):
        override_node = dict(override.get("node_template") or {})
        node_template = {
            "node_type": str(override_node.get("node_type") or node_template.get("node_type") or "process").strip(),
            "affair_type": str(override_node.get("affair_type") or node_template.get("affair_type") or affair_uid).strip(),
            "config": dict(override_node.get("config") or node_template.get("config") or {}),
            "inputs": dict(override_node.get("inputs") or node_template.get("inputs") or {}),
            "outputs": dict(override_node.get("outputs") or node_template.get("outputs") or {}),
            "payload_defaults": dict(override_node.get("payload_defaults") or node_template.get("payload_defaults") or {}),
            "flags": dict(override_node.get("flags") or node_template.get("flags") or {}),
        }

    source_py_path = str((affair_dir / "affair.py").resolve())
    params_json_path = str((affair_dir / "affair.json").resolve())
    doc_md_path = str((affair_dir / "affair.md").resolve())

    record_uid = f"{owner}:{folder_name}:{manifest_hash[:12]}"

    record: Dict[str, Any] = {
        "record_uid": record_uid,
        "affair_uid": affair_uid,
        "display_name": display_name,
        "folder_name": folder_name,
        "name": display_name,
        "version": str(manifest.get("version") or "0.0.0"),
        "domain": domain,
        "owner": owner,
        "affair_dir": str(affair_dir),
        "source_py_path": source_py_path,
        "params_json_path": params_json_path,
        "doc_md_path": doc_md_path,
        "source": source_py_path,
        "manifest_path": str(manifest_path.resolve()),
        "runner": {
            "module": module,
            "callable": callable_name,
            "pass_mode": pass_mode,
            "kwargs": dict(runner.get("kwargs") or {}) if isinstance(runner.get("kwargs"), Mapping) else {},
            "source_py_path": source_py_path,
        },
        "node_template": node_template,
        "docs": {
            "md_path": docs_md_path,
        },
        "summary": str(override.get("summary") or manifest.get("summary") or "").strip(),
        "keywords": list(override.get("keywords") or manifest.get("keywords") or [])
        if isinstance(override.get("keywords") or manifest.get("keywords") or [], list)
        else [],
        "docs_index": {"md_path": docs_md_path},
        "governance_tags": list(override.get("governance_tags") or manifest.get("governance_tags") or [])
        if isinstance(override.get("governance_tags") or manifest.get("governance_tags") or [], list)
        else [],
        "status": "active",
        "enabled": bool(manifest.get("enabled", True)),
        "manifest_hash": manifest_hash,
        "created_at": now_text,
        "updated_at": now_text,
        "last_synced_at": now_text,
        "source_workspace": "",
        "collision_history": [],
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

