"""事务导入与命名治理工具。

本模块用于把用户功能程序导入为标准三件套事务目录，并触发事务数据库同步。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping

from autodoengine.utils.common.affair_sync import (
    default_user_affairs_root,
    sync_affair_databases,
)


@dataclass(frozen=True)
class AffairImportResult:
    """事务导入结果。

    Args:
        requested_name: 用户请求的事务名。
        final_name: 最终写入事务目录名。
        affair_uid: 事务 UID。
        renamed: 是否发生重命名。
        affair_dir: 目标事务目录。
        source_py_path: 目标事务逻辑文件路径。
        params_json_path: 目标参数文件路径。
        doc_md_path: 目标说明文档路径。
        collision_history: 命名冲突历史记录。
        warnings: 导入警告。
    """

    requested_name: str
    final_name: str
    affair_uid: str
    renamed: bool
    affair_dir: Path
    source_py_path: Path
    params_json_path: Path
    doc_md_path: Path
    collision_history: List[str]
    warnings: List[str]


def _next_available_name(*, base_name: str, affairs_root: Path, existing_uids: set[str]) -> tuple[str, List[str]]:
    """计算可用事务名并记录冲突链。

    Args:
        base_name: 期望事务名。
        affairs_root: 事务根目录。
        existing_uids: 已存在事务 UID 集合。

    Returns:
        二元组：(最终名称, 冲突链)。
    """

    collision_history: List[str] = []
    candidate = base_name
    index = 1
    while True:
        folder_exists = (affairs_root / candidate).exists()
        uid_exists = candidate in existing_uids
        if not folder_exists and not uid_exists:
            return candidate, collision_history

        collision_history.append(candidate)
        index += 1
        candidate = f"{base_name}_v{index}"


def _load_json_mapping(path: Path) -> Mapping[str, Any]:
    """读取并校验 JSON 对象。

    Args:
        path: JSON 文件路径。

    Returns:
        JSON 对象映射。

    Raises:
        ValueError: 当 JSON 不是对象时抛出。
    """

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"参数文件必须是 JSON 对象：{path}")
    return data


def _build_default_affair_doc(*, affair_name: str) -> str:
    """生成默认事务说明文档。

    Args:
        affair_name: 事务名。

    Returns:
        Markdown 文本。
    """

    return (
        f"# {affair_name}\n\n"
        "## 事务用途\n\n"
        "- 请补充事务用途说明。\n\n"
        "## 适用场景\n\n"
        "- 请补充适用场景。\n\n"
        "## 参数说明\n\n"
        "- 参数来自 `affair.json`，请逐项补充含义。\n\n"
        "## 输出结果\n\n"
        "- 请补充产物说明。\n\n"
        "## 基本示例\n\n"
        "```python\n"
        "from pathlib import Path\n"
        "import autodoengine as aok\n\n"
        f"outputs = aok.run_affair(\"{affair_name}\", config_path=\"./affair.json\", workspace_root=Path.cwd())\n"
        "print(outputs)\n"
        "```\n"
    )


def import_user_affair(
    *,
    workspace_root: Path,
    source_py_path: Path,
    source_params_json_path: Path | None = None,
    source_doc_md_path: Path | None = None,
    affair_name: str | None = None,
    strict: bool = False,
) -> AffairImportResult:
    """导入用户事务三件套并写入事务管理系统。

    Args:
        workspace_root: 用户工作区根目录。
        source_py_path: 功能程序文件路径。
        source_params_json_path: 参数模板 JSON 路径，可选。
        source_doc_md_path: 说明文档 MD 路径，可选。
        affair_name: 事务名，可选；为空时使用源文件名。
        strict: 严格模式，存在同步错误时抛出异常。

    Returns:
        导入结果对象。

    Raises:
        FileNotFoundError: 输入文件不存在时抛出。
        ValueError: 输入参数非法时抛出。
    """

    workspace = workspace_root.resolve()
    source_py = source_py_path.resolve()
    if not source_py.exists():
        raise FileNotFoundError(f"事务逻辑文件不存在：{source_py}")

    requested_name = str(affair_name or source_py.stem).strip()
    if not requested_name:
        raise ValueError("事务名不能为空")

    user_affairs_root = default_user_affairs_root(workspace)
    user_affairs_root.mkdir(parents=True, exist_ok=True)

    runtime_registry = sync_affair_databases(workspace_root=workspace, strict=False).records
    existing_uids = {str(item.get("affair_uid") or "").strip() for item in runtime_registry}

    final_name, collision_history = _next_available_name(
        base_name=requested_name,
        affairs_root=user_affairs_root,
        existing_uids=existing_uids,
    )

    target_dir = (user_affairs_root / final_name).resolve()
    target_dir.mkdir(parents=True, exist_ok=False)

    target_py = target_dir / "affair.py"
    target_json = target_dir / "affair.json"
    target_md = target_dir / "affair.md"

    shutil.copy2(source_py, target_py)

    warnings: List[str] = []
    if source_params_json_path is not None:
        source_json = source_params_json_path.resolve()
        if not source_json.exists():
            raise FileNotFoundError(f"事务参数文件不存在：{source_json}")
        _ = _load_json_mapping(source_json)
        shutil.copy2(source_json, target_json)
    else:
        target_json.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")
        warnings.append("未提供参数模板，已创建空的 affair.json")

    if source_doc_md_path is not None:
        source_md = source_doc_md_path.resolve()
        if not source_md.exists():
            raise FileNotFoundError(f"事务说明文档不存在：{source_md}")
        shutil.copy2(source_md, target_md)
    else:
        target_md.write_text(_build_default_affair_doc(affair_name=final_name), encoding="utf-8")
        warnings.append("未提供说明文档，已生成默认的 affair.md 模板")

    sync_result = sync_affair_databases(workspace_root=workspace, strict=strict)

    affair_uid = final_name
    for record in sync_result.records:
        if str(record.get("folder_name") or "").strip() == final_name and str(record.get("owner") or "") == "user":
            affair_uid = str(record.get("affair_uid") or final_name).strip() or final_name
            break

    return AffairImportResult(
        requested_name=requested_name,
        final_name=final_name,
        affair_uid=affair_uid,
        renamed=final_name != requested_name,
        affair_dir=target_dir,
        source_py_path=target_py,
        params_json_path=target_json,
        doc_md_path=target_md,
        collision_history=collision_history,
        warnings=warnings,
    )
