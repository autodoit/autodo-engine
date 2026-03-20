"""事务管理系统公共模块。"""

from __future__ import annotations

from autodoengine.utils.common.affair_db import create_empty_registry, load_registry, save_registry
from autodoengine.utils.common.affair_manager import AffairImportResult, import_user_affair
from autodoengine.utils.common.affair_permissions import can_user_override, validate_domain_owner, validate_user_record
from autodoengine.utils.common.affair_registry import build_records_from_root, scan_affair_manifests, validate_manifest
from autodoengine.utils.common.affair_sync import AffairSyncResult, build_runtime_registry, merge_runtime_records, sync_affair_databases

__all__ = [
    "create_empty_registry",
    "load_registry",
    "save_registry",
    "AffairImportResult",
    "import_user_affair",
    "can_user_override",
    "validate_domain_owner",
    "validate_user_record",
    "build_records_from_root",
    "scan_affair_manifests",
    "validate_manifest",
    "AffairSyncResult",
    "build_runtime_registry",
    "merge_runtime_records",
    "sync_affair_databases",
]

