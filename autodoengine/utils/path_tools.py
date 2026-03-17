"""通用路径与配置预处理工具。"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json_or_py(config_path: Path) -> Dict[str, Any]:
    """载入 .json 或 .py 配置文件并返回字典。"""

    suffix = config_path.suffix.lower()
    if suffix == ".json":
        text = config_path.read_text(encoding="utf-8-sig")
        return json.loads(text) if text.strip() else {}
    if suffix == ".py":
        module_name = f"config_{config_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, config_path)
        if spec is None or spec.loader is None:
            raise ValueError("无法加载配置模块")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "CONFIG"):
            raise ValueError("Python 配置文件需包含 CONFIG 字典")
        return getattr(module, "CONFIG")
    raise ValueError("配置文件必须为 .json 或 .py")


def resolve_path(raw: str, config_path: Path, env_root_var: str = "PROJECT_ROOT") -> Path:
    """将配置中的路径解析为绝对 Path。"""

    if not raw:
        return Path()
    expanded = os.path.expanduser(str(raw))
    path_obj = Path(expanded)
    if path_obj.is_absolute():
        try:
            return path_obj.resolve()
        except Exception:
            return path_obj

    env_root = os.getenv(env_root_var)
    if env_root:
        return (Path(env_root) / path_obj).resolve()

    return (config_path.parent / path_obj).resolve()


def find_repo_root(start: Path) -> Path:
    """从给定路径向上查找仓库根目录。"""

    cursor = Path(start).resolve()
    if cursor.is_file():
        cursor = cursor.parent
    for candidate in [cursor, *cursor.parents]:
        if (
            (candidate / "pyproject.toml").exists()
            or (candidate / "requirements.txt").exists()
            or (candidate / ".git").exists()
        ):
            return candidate
    return cursor


def resolve_path_from_base(raw: str, *, base_dir: Path) -> Path:
    """展开环境变量与 `~`，并按 base_dir 解析相对路径。"""

    if not raw or not str(raw).strip():
        raise ValueError("路径配置为空，无法解析。")

    expanded = os.path.expandvars(os.path.expanduser(str(raw).strip()))
    path_obj = Path(expanded)
    if path_obj.is_absolute():
        try:
            return path_obj.resolve()
        except Exception:
            return path_obj

    try:
        return (Path(base_dir).resolve() / path_obj).resolve()
    except Exception:
        return Path(base_dir).resolve() / path_obj


def resolve_config_paths(cfg: dict, config_path: Path, workspace_root: Path | None = None) -> dict:
    """解析配置文件中的路径字段。"""

    cfg = dict(cfg)

    config_path = config_path.resolve()
    config_dir = config_path.parent
    repo_root = workspace_root.resolve() if workspace_root is not None else find_repo_root(config_dir)

    def _to_abs_dir(raw_dir: str | None, *, default_dir: Path) -> Path:
        if not raw_dir or not str(raw_dir).strip():
            return default_dir
        return resolve_path_from_base(str(raw_dir), base_dir=default_dir)

    workflow_dir_raw = cfg.get("workflow_dir")
    workflow_dir_default = (
        Path(str(workflow_dir_raw))
        if isinstance(workflow_dir_raw, str) and workflow_dir_raw.strip()
        else repo_root
    )
    if not workflow_dir_default.is_absolute():
        workflow_dir_default = (repo_root / workflow_dir_default).resolve()

    input_base_dir = _to_abs_dir(cfg.get("input_base_dir"), default_dir=repo_root)
    output_default_dir = repo_root if workspace_root is not None else workflow_dir_default
    output_base_dir = _to_abs_dir(cfg.get("output_base_dir"), default_dir=output_default_dir)

    def resolve_one(path_value: str | None, *, kind: str) -> str | None:
        if not path_value:
            return None

        expanded = os.path.expandvars(os.path.expanduser(str(path_value)))
        path_obj = Path(expanded)
        if path_obj.is_absolute():
            return str(path_obj)

        base_dir = input_base_dir if kind == "input" else output_base_dir
        candidate = resolve_path_from_base(str(path_value), base_dir=base_dir)

        if kind == "input" and not candidate.exists():
            fallback = resolve_path_from_base(str(path_value), base_dir=repo_root)
            if fallback.exists():
                return str(fallback)

        return str(candidate)

    cfg["_resolved_pdf_dir"] = resolve_one(cfg.get("pdf_dir"), kind="input")
    cfg["_resolved_output_dir"] = resolve_one(cfg.get("output_dir"), kind="output")

    return cfg


def resolve_paths_to_absolute(
    cfg: Dict[str, Any],
    *,
    workspace_root: Path,
    path_keys: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """将配置中的路径字段统一解析为绝对路径（递归）。"""

    if workspace_root is None:
        raise ValueError("workspace_root 不能为空")
    workspace_root = Path(workspace_root)
    if not workspace_root.is_absolute():
        workspace_root = workspace_root.resolve()

    default_keys = {
        "output_dir",
        "input_table_csv",
        "aof_md_path",
        "emit_python_path",
        "emit_compiled_workflow_path",
        "workflow_path",
        "bibtex_path",
        "input_bibtex_path",
        "output_bibtex_path",
        "docs_path",
        "chunks_path",
        "pdf_dir",
        "input_pdf_dir",
        "output_md_dir",
        "output_log",
        "output_structured_dir",
        "secrets_file",
        "config_path",
        "input_documents_dir",
        "unit_db_dir",
        "input_docs_jsonl",
        "input_chunks_jsonl",
        "input_matrix_jsonl",
        "candidate_csv",
        "excluded_csv",
        "report_path",
        "index_dir",
        "keyword_set_json",
        "input_keywords",
        "reference_materials_dir",
    }
    keys = default_keys if path_keys is None else set(path_keys)

    def _to_abs(value: str) -> str:
        expanded = os.path.expandvars(os.path.expanduser(str(value).strip()))
        path_obj = Path(expanded)
        if path_obj.is_absolute():
            try:
                return str(path_obj.resolve())
            except Exception:
                return str(path_obj)
        try:
            return str((workspace_root / path_obj).resolve())
        except Exception:
            return str(workspace_root / path_obj)

    def _walk(obj: Any, *, parent_key: str | None = None) -> Any:
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for key, value in obj.items():
                if isinstance(key, str) and key in keys and isinstance(value, str) and value.strip():
                    out[key] = _to_abs(value)
                else:
                    out[key] = _walk(value, parent_key=str(key) if isinstance(key, str) else None)
            return out
        if isinstance(obj, list):
            return [_walk(item, parent_key=parent_key) for item in obj]
        return obj

    return _walk(dict(cfg))


def resolve_workflow_config_path(
    raw: str,
    *,
    workspace_root: Path,
    config_path: Path | None = None,
) -> Path:
    """将 run 列表中的 workflow 配置路径统一解析为绝对路径。"""

    if not raw or not str(raw).strip():
        raise ValueError("workflow 配置路径为空，无法解析。")

    workspace_root = Path(workspace_root)
    if not workspace_root.is_absolute():
        workspace_root = workspace_root.resolve()

    path_obj = Path(os.path.expandvars(os.path.expanduser(str(raw).strip())))
    if path_obj.is_absolute():
        try:
            return path_obj.resolve()
        except Exception:
            return path_obj

    candidates: List[Path] = [resolve_path_from_base(str(path_obj), base_dir=workspace_root)]

    if config_path is not None:
        config_dir = Path(config_path).resolve().parent
        candidates.append(resolve_path_from_base(str(path_obj), base_dir=config_dir))

    parts = [part for part in path_obj.parts if part not in {".", ""}]
    if parts and parts[0] == workspace_root.name:
        trimmed = Path(*parts[1:]) if len(parts) > 1 else Path()
        parent_root = workspace_root.parent
        candidates.append(resolve_path_from_base(str(path_obj), base_dir=parent_root))
        if str(trimmed):
            candidates.append(resolve_path_from_base(str(trimmed), base_dir=workspace_root))

    seen: set[str] = set()
    normalized_candidates: List[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        normalized_candidates.append(candidate)

    for candidate in normalized_candidates:
        if candidate.exists():
            return candidate

    return normalized_candidates[0]


def resolve_path_with_workspace_root(raw: str, *, workspace_root: Path) -> Path:
    """以 workspace_root 为唯一基准解析单个路径。"""

    if not raw or not str(raw).strip():
        return Path()

    try:
        return resolve_path_from_base(str(raw), base_dir=workspace_root)
    except ValueError:
        return Path()
