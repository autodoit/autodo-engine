"""v4 对外公开 API。"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import tempfile
import traceback
from contextlib import contextmanager
from hashlib import sha256
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from autodoengine.core.enums import TaskStatus
from autodoengine.core.types import DecisionResult
from autodoengine.flow_graph import load_graph_from_file
from autodoengine.flow_graph.models import Graph
from autodoengine.scheduling.task_loop import run_task_step as _run_task_step
from autodoengine.scheduling.task_loop import run_task_until_terminal as _run_task_until_terminal
from autodoengine.scheduling.task_loop import run_task_until_wait as _run_task_until_wait
from autodoengine.taskdb import bootstrap_runtime_storage
from autodoengine.taskdb import graph_registry, task_store
from autodoengine.taskdb.department_store import (
    get_department as _get_department,
    list_department_members as _list_department_members,
    list_departments as _list_departments,
)
from autodoengine.taskdb.request_store import (
    create_request as _create_request,
    get_request as _get_request,
    list_requests as _list_requests,
    list_task_requests as _list_task_requests,
    mark_request_blocked as _mark_request_blocked,
    mark_request_completed as _mark_request_completed,
    mark_request_failed as _mark_request_failed,
    mark_request_running as _mark_request_running,
    请求状态_已完成,
    请求状态_已失败,
    请求状态_已阻断,
    请求状态_待调度,
)
from autodoengine.taskdb import (
    build_blocked_governance_view as _build_blocked_governance_view,
    build_decision_department_view as _build_decision_department_view,
    build_task_full_chain_view as _build_task_full_chain_view,
)
from autodoengine.taskdb import log_store
from autodoengine.taskdb.storage_paths import get_runtime_store_dirs, get_runtime_store_files
from autodoengine.utils.affair_registry import build_registry, resolve_runner
from autodoengine.utils.common.affair_manager import import_user_affair as _import_user_affair
from autodoengine.utils.common.affair_sync import SCHEMA_VERSION, build_runtime_registry, get_affair_registry_paths as _get_affair_registry_paths, sync_affair_databases
from autodoengine.utils.path_tools import (
    load_json_or_py,
    resolve_paths_to_absolute,
    resolve_paths_to_absolute_with_audit,
    resolve_portable_path,
)
from autodoengine.utils.runtime_context import get_runtime_context, set_runtime_context


def _load_tools_module() -> Any:
    """按需加载工具模块。

    Returns:
        优先返回 `autodokit.tools`，未安装时回退到 `autodoengine.tools`。

    Raises:
        ModuleNotFoundError: 当外部与内置工具模块均不可用时抛出。
    """

    try:
        return importlib.import_module("autodokit.tools")
    except ModuleNotFoundError:
        try:
            return importlib.import_module("autodoengine.tools")
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "未找到可用工具模块（autodokit.tools/autodoengine.tools）。"
            ) from exc


def _load_tools_module_with_attrs(*required_attrs: str) -> Any:
    """加载满足指定接口的工具模块。

    Args:
        *required_attrs: 必须存在的属性名。

    Returns:
        满足接口要求的工具模块。

    Raises:
        KeyError: 当没有模块满足要求时抛出。
    """

    candidates: list[Any] = []
    for module_name in ("autodokit.tools", "autodoengine.tools"):
        try:
            candidates.append(importlib.import_module(module_name))
        except ModuleNotFoundError:
            continue

    for module in candidates:
        if all(hasattr(module, attr) for attr in required_attrs):
            return module

    raise KeyError(f"工具模块未提供所需接口：{', '.join(required_attrs)}")


def _normalize_workspace_root(workspace_root: str | Path | None) -> Path:
    """规范化工作区根目录。

    Args:
        workspace_root: 工作区根目录。

    Returns:
        绝对路径形式的工作区根目录。
    """

    if workspace_root is None:
        return Path.cwd().resolve()
    return resolve_portable_path(str(workspace_root), base_dir=Path.cwd())


def _normalize_affair_outputs(result: Any) -> List[Path]:
    """将事务返回结果归一化为路径列表。

    Args:
        result: 事务返回值。

    Returns:
        路径对象列表。
    """

    if result is None:
        return []

    if isinstance(result, dict):
        payload = result.get("output_payload") if isinstance(result.get("output_payload"), dict) else {}
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
        return [Path(str(item)) for item in artifacts]

    if isinstance(result, (str, Path)):
        return [Path(str(result))]

    if isinstance(result, list):
        return [Path(str(item)) for item in result]

    if isinstance(result, tuple):
        return [Path(str(item)) for item in result]

    return [Path(str(result))]


@contextmanager
def _runtime_context_scope(*, workspace_root: Path, affair_uid: str, config_path: Path) -> Any:
    """临时注入运行时上下文并在退出时恢复。"""

    previous_context = get_runtime_context()
    global_config_path = workspace_root / "config" / "config.json"
    if not global_config_path.exists():
        global_config_path = None

    set_runtime_context(
        global_config_path=global_config_path,
        current_affair_uid=affair_uid,
        current_affair_config_path=config_path,
    )
    try:
        yield
    finally:
        set_runtime_context(
            global_config_path=previous_context.global_config_path,
            current_affair_uid=previous_context.current_affair_uid,
            current_affair_config_path=previous_context.current_affair_config_path,
        )


def _serialize_dataclass_or_value(value: Any) -> Any:
    """序列化 dataclass 或原始值。

    Args:
        value: 待序列化对象。

    Returns:
        适合 JSON 输出的对象。
    """

    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


def _load_module_from_file(source_py_path: str | Path) -> Any:
    """按源码文件路径加载事务模块。

    Args:
        source_py_path: 事务源码路径。

    Returns:
        Python 模块对象。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ImportError: 文件无法加载为模块时抛出。
    """

    source_path = resolve_portable_path(str(source_py_path), base_dir=Path.cwd())
    if not source_path.exists():
        raise FileNotFoundError(f"事务源码文件不存在：{source_path}")

    module_name = f"autodoengine_dynamic_affair_{sha256(str(source_path).encode('utf-8')).hexdigest()[:16]}"
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载事务源码模块：{source_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_graph(file_path: str) -> Graph:
    """公开的图加载入口。

    Args:
        file_path: 静态图 JSON 文件路径。

    Returns:
        Graph: 图对象。

    Raises:
        FileNotFoundError: 当文件不存在时抛出。

    Examples:
        >>> # doctest: +SKIP
        >>> graph = load_graph("demos/data/graph.json")
    """

    target = resolve_portable_path(file_path, base_dir=Path.cwd())
    if not target.exists():
        raise FileNotFoundError(f"图文件不存在：{target}")
    return load_graph_from_file(str(target))


def bootstrap_runtime(base_dir: str) -> None:
    """公开的运行时初始化入口。"""

    bootstrap_runtime_storage(base_dir)


def register_graph(graph: Graph) -> None:
    """公开的图注册入口。"""

    graph_registry.register_graph(graph)


def create_task(title: str, goal_text: str, current_node_uid: str, parent_task_uid: str | None = None) -> dict[str, object]:
    """公开的任务创建入口。"""

    return task_store.create_task(
        title=title,
        goal_text=goal_text,
        current_node_uid=current_node_uid,
        parent_task_uid=parent_task_uid,
    )


def create_task_request(
    request_type: str,
    target_affair_uid: str,
    payload: dict[str, Any] | None = None,
    task_uid: str | None = None,
    source_object_type: str = "",
    source_object_uid: str = "",
    node_code: str = "",
    config_path: str = "",
    priority_score: float = 0.0,
    source: str = "任务系统",
    request_contract: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """创建事务请求。"""

    return _create_request(
        request_type=request_type,
        target_affair_uid=target_affair_uid,
        payload=payload,
        task_uid=task_uid,
        source_object_type=source_object_type,
        source_object_uid=source_object_uid,
        node_code=node_code,
        config_path=config_path,
        priority_score=priority_score,
        source=source,
        request_contract=request_contract,
        metadata=metadata,
    )


def create_task_request_from_project_node(
    *,
    project_config_path: str | Path,
    node_code: str,
    task_uid: str | None = None,
    request_type: str = "事务执行",
    target_affair_uid: str | None = None,
    source_object_type: str = "节点",
    source_object_uid: str | None = None,
    priority_score: float = 0.0,
    source: str = "项目经理",
    payload: dict[str, Any] | None = None,
    request_contract: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """根据项目级配置与节点编码构造标准事务请求。"""

    resolved_project_config_path = resolve_portable_path(str(project_config_path), base_dir=Path.cwd())
    project_config = load_json_or_py(resolved_project_config_path)

    normalized_node_code = str(node_code or "").strip().upper()
    if not normalized_node_code:
        raise ValueError("node_code 不能为空")

    node_inputs = project_config.get("node_inputs")
    if not isinstance(node_inputs, dict):
        raise KeyError("项目配置缺少 node_inputs")
    if normalized_node_code not in node_inputs:
        raise KeyError(f"node_inputs 中不存在节点：{normalized_node_code}")

    workspace_root_text = str(project_config.get("workspace_root") or "").strip()
    workspace_root = (
        resolve_portable_path(workspace_root_text, base_dir=resolved_project_config_path.parent)
        if workspace_root_text
        else resolved_project_config_path.parent
    )
    resolved_node_config_path = resolve_portable_path(str(node_inputs[normalized_node_code]), base_dir=workspace_root)

    node_contracts = project_config.get("node_contracts")
    project_node_contract = (
        dict(node_contracts.get(normalized_node_code) or {})
        if isinstance(node_contracts, dict) and isinstance(node_contracts.get(normalized_node_code), dict)
        else {}
    )
    merged_request_contract = dict(project_node_contract)
    merged_request_contract.update(dict(request_contract or {}))

    resolved_affair_uid = str(target_affair_uid or "").strip()
    if not resolved_affair_uid:
        paths_payload = project_config.get("paths")
        registry_path_text = str((paths_payload or {}).get("affair_entry_registry_path") or "").strip()
        if registry_path_text:
            resolved_registry_path = resolve_portable_path(registry_path_text, base_dir=workspace_root)
            registry_payload = load_json_or_py(resolved_registry_path)
            for item in registry_payload.get("records", []):
                if not isinstance(item, dict):
                    continue
                record_node_code = str(item.get("node_code") or "").strip().upper()
                affair_uid = str(item.get("affair_uid") or "").strip()
                if record_node_code == normalized_node_code and affair_uid:
                    resolved_affair_uid = affair_uid
                    break
    if not resolved_affair_uid:
        raise KeyError(f"无法为节点推断 target_affair_uid：{normalized_node_code}")

    next_payload = dict(payload or {})
    next_payload.setdefault("workspace_root", str(workspace_root))
    next_payload.setdefault("project_config_path", str(resolved_project_config_path))
    next_payload.setdefault("node_config_path", str(resolved_node_config_path))

    next_metadata = dict(metadata or {})
    next_metadata.setdefault("project_config_path", str(resolved_project_config_path))
    next_metadata.setdefault("workspace_root", str(workspace_root))
    next_metadata.setdefault("node_code", normalized_node_code)

    return create_task_request(
        request_type=request_type,
        target_affair_uid=resolved_affair_uid,
        payload=next_payload,
        task_uid=task_uid,
        source_object_type=source_object_type,
        source_object_uid=source_object_uid or normalized_node_code,
        node_code=normalized_node_code,
        config_path=str(resolved_node_config_path),
        priority_score=priority_score,
        source=source,
        request_contract=merged_request_contract,
        metadata=next_metadata,
    )


def get_task_request(request_uid: str) -> Dict[str, Any]:
    """读取单个事务请求。"""

    return _get_request(request_uid)


def list_task_requests(task_uid: str | None = None, status: str | None = None) -> List[Dict[str, Any]]:
    """列出事务请求。"""

    if task_uid:
        return _list_task_requests(task_uid)
    return _list_requests(status=status)


def _load_json_mapping(file_path: Path) -> dict[str, Any]:
    """读取 JSON/Python 配置并确保为字典。"""

    payload = load_json_or_py(file_path)
    if not isinstance(payload, dict):
        raise ValueError(f"配置根对象必须是字典：{file_path}")
    return payload


def _import_module_with_repo_fallback(module_name: str, *, workspace_root: Path) -> Any:
    """导入模块；若缺少 sibling 仓库安装，则回退注入源码根目录。"""

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        pass

    candidate_roots = [
        workspace_root.parent.parent / "autodo-kit",
        Path(__file__).resolve().parents[2] / "autodo-kit",
        workspace_root.parent.parent / "autodo-engine",
        Path(__file__).resolve().parents[2] / "autodo-engine",
    ]
    seen: set[str] = set()
    for root in candidate_roots:
        resolved = str(root.resolve())
        if resolved in seen or not root.exists():
            continue
        seen.add(resolved)
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue

    return importlib.import_module(module_name)


def _node_uid_to_code(node_uid: str) -> str:
    """把图节点 UID 归一化为 A010 这类节点编码。"""

    normalized = str(node_uid or "").strip().lower()
    if normalized.startswith("n_"):
        normalized = normalized[2:]
    return normalized.upper()


def _slice_project_nodes(node_sequence: list[str], start_node: str | None, end_node: str | None) -> list[str]:
    """按起止节点切主链片段。"""

    if not node_sequence:
        return []

    start = str(start_node or node_sequence[0]).strip().upper()
    end = str(end_node or node_sequence[-1]).strip().upper()
    if start not in node_sequence:
        raise KeyError(f"start_node 不在主链图中：{start}")
    if end not in node_sequence:
        raise KeyError(f"end_node 不在主链图中：{end}")

    start_index = node_sequence.index(start)
    end_index = node_sequence.index(end)
    if start_index > end_index:
        raise ValueError(f"start_node 必须早于 end_node：{start} > {end}")
    return node_sequence[start_index : end_index + 1]


def _resolve_project_mainflow_context(project_config_path: str | Path) -> Dict[str, Any]:
    """解析项目主链运行上下文。"""

    resolved_project_config_path = resolve_portable_path(str(project_config_path), base_dir=Path.cwd())
    project_config = _load_json_mapping(resolved_project_config_path)
    runtime = project_config.get("runtime") if isinstance(project_config.get("runtime"), dict) else {}
    paths_payload = project_config.get("paths") if isinstance(project_config.get("paths"), dict) else {}

    workspace_root_text = str(project_config.get("workspace_root") or "").strip()
    workspace_root = (
        resolve_portable_path(workspace_root_text, base_dir=resolved_project_config_path.parent)
        if workspace_root_text
        else resolved_project_config_path.parent
    )
    if not workspace_root.exists():
        raise FileNotFoundError(f"workspace_root 不存在：{workspace_root}")

    graph_path_text = str(runtime.get("workflow_graph_path") or "").strip()
    if not graph_path_text:
        raise KeyError("项目配置缺少 runtime.workflow_graph_path")
    graph_path = resolve_portable_path(graph_path_text, base_dir=workspace_root.parent)
    if not graph_path.exists():
        raise FileNotFoundError(f"workflow_graph_path 不存在：{graph_path}")

    registry_path_text = str(paths_payload.get("affair_entry_registry_path") or "").strip()
    if not registry_path_text:
        raise KeyError("项目配置缺少 paths.affair_entry_registry_path")
    registry_path = resolve_portable_path(registry_path_text, base_dir=workspace_root)
    if not registry_path.exists():
        raise FileNotFoundError(f"affair_entry_registry_path 不存在：{registry_path}")

    graph_payload = _load_json_mapping(graph_path)
    registry_payload = _load_json_mapping(registry_path)

    node_sequence: list[str] = []
    for item in graph_payload.get("nodes", []):
        if not isinstance(item, dict):
            continue
        if not bool(item.get("enabled", True)):
            continue
        node_uid = str(item.get("node_uid") or "").strip()
        if not node_uid:
            continue
        node_sequence.append(_node_uid_to_code(node_uid))

    records: dict[str, dict[str, Any]] = {}
    for item in registry_payload.get("records", []):
        if not isinstance(item, dict):
            continue
        node_code = str(item.get("node_code") or "").strip().upper()
        affair_uid = str(item.get("affair_uid") or "").strip()
        raw_config_path = str(item.get("config_path") or "").strip()
        if not node_code:
            continue
        records[node_code] = {
            "node_code": node_code,
            "affair_uid": affair_uid,
            "config_path": str(resolve_portable_path(raw_config_path, base_dir=workspace_root)) if raw_config_path else "",
            "implemented": bool(item.get("implemented", False)),
            "module": str(item.get("module") or "").strip(),
            "callable": str(item.get("callable") or "execute").strip() or "execute",
            "source_py_path": str(item.get("source_py_path") or "").strip(),
        }

    project_payload = project_config.get("project") if isinstance(project_config.get("project"), dict) else {}
    return {
        "project_config_path": resolved_project_config_path,
        "project_config": project_config,
        "runtime": runtime,
        "workspace_root": workspace_root,
        "graph_path": graph_path,
        "registry_path": registry_path,
        "node_sequence": node_sequence,
        "records": records,
        "project_name": str(project_payload.get("project_name") or project_config.get("workflow_name") or workspace_root.name),
        "project_goal": str(project_payload.get("project_goal") or ""),
    }


def validate_project_mainflow(
    *,
    project_config_path: str | Path,
    start_node: str | None = None,
    end_node: str | None = None,
) -> Dict[str, Any]:
    """验证项目主链配置是否可由 AOE 正式运行。"""

    context = _resolve_project_mainflow_context(project_config_path)
    runtime = context["runtime"]
    target_nodes = _slice_project_nodes(
        context["node_sequence"],
        start_node or str(runtime.get("start_node") or "").strip() or None,
        end_node or str(runtime.get("end_node") or "").strip() or None,
    )
    action_routing = runtime.get("user_action_routing") if isinstance(runtime.get("user_action_routing"), dict) else {}
    required_actions = ["execute", "continue", "pause", "retry", "fallback", "stop", "gate_pass"]
    missing_actions = [item for item in required_actions if item not in action_routing]

    reports: list[dict[str, Any]] = []
    missing_registry: list[str] = []
    missing_config: list[str] = []
    unimplemented: list[str] = []
    for node_code in target_nodes:
        record = context["records"].get(node_code)
        if record is None:
            missing_registry.append(node_code)
            reports.append({"node_code": node_code, "ok": False, "reason": "missing_registry"})
            continue

        config_exists = bool(record.get("config_path")) and Path(str(record["config_path"])).exists()
        implemented = bool(record.get("implemented", False))
        if not config_exists:
            missing_config.append(node_code)
        if not implemented:
            unimplemented.append(node_code)
        reports.append(
            {
                "node_code": node_code,
                "ok": config_exists and implemented,
                "implemented": implemented,
                "config_exists": config_exists,
                "affair_uid": str(record.get("affair_uid") or ""),
                "config_path": str(record.get("config_path") or ""),
            }
        )

    return {
        "ok": not missing_registry and not missing_config and not unimplemented and not missing_actions,
        "project_name": context["project_name"],
        "project_goal": context["project_goal"],
        "project_config_path": str(context["project_config_path"]),
        "workspace_root": str(context["workspace_root"]),
        "graph_path": str(context["graph_path"]),
        "registry_path": str(context["registry_path"]),
        "start_node": target_nodes[0] if target_nodes else None,
        "end_node": target_nodes[-1] if target_nodes else None,
        "target_nodes": target_nodes,
        "node_count": len(target_nodes),
        "missing_registry": missing_registry,
        "missing_config": missing_config,
        "unimplemented": unimplemented,
        "missing_actions": missing_actions,
        "reports": reports,
    }


def _run_project_registered_affair(
    *,
    project_config_path: str | Path,
    node_code: str,
    config_path: Path,
    workspace_root: Path,
) -> List[Path] | None:
    """按项目注册表中的 module/callable 回退执行事务。"""

    context = _resolve_project_mainflow_context(project_config_path)
    record = context["records"].get(str(node_code or "").strip().upper()) or {}
    module_name = str(record.get("module") or "").strip()
    callable_name = str(record.get("callable") or "execute").strip() or "execute"
    source_py_path = str(record.get("source_py_path") or "").strip()
    if not module_name and not source_py_path:
        return None

    if module_name:
        module = _import_module_with_repo_fallback(module_name, workspace_root=workspace_root)
    else:
        module = _load_module_from_file(resolve_portable_path(source_py_path, base_dir=workspace_root))

    callable_obj = getattr(module, callable_name)
    try:
        result = callable_obj(config_path, workspace_root=workspace_root)
    except TypeError:
        result = callable_obj(config_path)
    return _normalize_affair_outputs(result)


def run_task_request(request_uid: str, *, simulate: bool = False) -> Dict[str, Any]:
    """执行单个事务请求并回写请求/任务状态。"""

    request = get_task_request(request_uid)
    current_status = str(request.get("status") or 请求状态_待调度)
    if current_status == 请求状态_已完成:
        raise ValueError(f"事务请求已完成，不能重复执行：{request_uid}")

    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    workspace_root_text = str(payload.get("workspace_root") or metadata.get("workspace_root") or "").strip()
    project_config_path_text = str(payload.get("project_config_path") or metadata.get("project_config_path") or "").strip()
    config_path_text = str(request.get("config_path") or payload.get("node_config_path") or "").strip()
    target_affair_uid = str(request.get("target_affair_uid") or "").strip()
    task_uid = str(request.get("task_uid") or "").strip() or None
    node_code = str(request.get("node_code") or target_affair_uid or "").strip()

    if not target_affair_uid:
        raise ValueError(f"事务请求缺少 target_affair_uid：{request_uid}")
    if not config_path_text:
        raise ValueError(f"事务请求缺少 config_path：{request_uid}")

    config_path = resolve_portable_path(config_path_text, base_dir=Path.cwd())
    if not config_path.exists():
        raise FileNotFoundError(f"事务请求配置不存在：{config_path}")

    workspace_root = (
        resolve_portable_path(workspace_root_text, base_dir=config_path.parent)
        if workspace_root_text
        else config_path.parent.parent
    )
    bootstrap_runtime(str(workspace_root))

    if task_uid:
        task_store.update_task_status(task_uid, TaskStatus.RUNNING)
        task_store.update_task_cursor(task_uid, current_node_uid=node_code, current_affair_uid=target_affair_uid)

    _mark_request_running(request_uid)
    log_store.append_runtime_event(
        "事务请求开始",
        {
            "task_uid": task_uid,
            "request_uid": request_uid,
            "node_code": node_code,
            "affair_uid": target_affair_uid,
            "simulate": bool(simulate),
        },
    )

    if simulate:
        result = {
            "mode": "simulate",
            "task_uid": task_uid,
            "request_uid": request_uid,
            "node_code": node_code,
            "affair_uid": target_affair_uid,
            "output_count": 0,
            "outputs": [],
        }
        _mark_request_completed(request_uid, result=result)
        log_store.append_runtime_event("事务请求完成", result)
        return {
            "status": "simulated",
            **result,
        }

    try:
        try:
            outputs = run_affair(
                target_affair_uid,
                config_path=config_path,
                workspace_root=workspace_root,
            )
        except KeyError:
            if not project_config_path_text:
                raise
            fallback_outputs = _run_project_registered_affair(
                project_config_path=project_config_path_text,
                node_code=node_code,
                config_path=config_path,
                workspace_root=workspace_root,
            )
            if fallback_outputs is None:
                raise
            outputs = fallback_outputs
    except Exception as exc:
        result = {
            "mode": "execute",
            "task_uid": task_uid,
            "request_uid": request_uid,
            "node_code": node_code,
            "affair_uid": target_affair_uid,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(limit=8),
        }
        _mark_request_failed(request_uid, result=result)
        if task_uid:
            task_store.mark_task_failed(task_uid)
        log_store.append_error_event("事务请求失败", result)
        return {
            "status": "failed",
            **result,
        }

    result = {
        "mode": "execute",
        "task_uid": task_uid,
        "request_uid": request_uid,
        "node_code": node_code,
        "affair_uid": target_affair_uid,
        "output_count": len(outputs),
        "outputs": [str(item) for item in outputs],
    }
    _mark_request_completed(request_uid, result=result)
    log_store.append_runtime_event("事务请求完成", result)
    return {
        "status": "completed",
        **result,
    }


def run_task_requests(task_uid: str, *, max_requests: int = 100, simulate: bool = False) -> List[Dict[str, Any]]:
    """消费任务下待调度的事务请求。"""

    requests = [item for item in list_task_requests(task_uid=task_uid) if str(item.get("status") or "") == 请求状态_待调度]
    results: list[dict[str, Any]] = []
    for request in requests[: max(0, int(max_requests)) or 0]:
        result = run_task_request(str(request.get("request_uid") or ""), simulate=simulate)
        results.append(result)
        if result.get("status") not in {"completed", "simulated"}:
            break

    if not results:
        return results

    refreshed = list_task_requests(task_uid=task_uid)
    statuses = {str(item.get("status") or "") for item in refreshed}
    if statuses and statuses <= {请求状态_已完成}:
        task_store.mark_task_completed(task_uid)
    elif 请求状态_已失败 in statuses:
        task_store.mark_task_failed(task_uid)
    elif 请求状态_已阻断 in statuses:
        task_store.update_task_status(task_uid, TaskStatus.BLOCKED)
    return results


def run_project_mainflow(
    *,
    project_config_path: str | Path,
    start_node: str | None = None,
    end_node: str | None = None,
    simulate: bool = False,
    source: str = "项目经理",
    decision_department_uid: str = "dept-default",
) -> Dict[str, Any]:
    """根据项目 config 生成事务请求并正式执行主链片段。"""

    context = _resolve_project_mainflow_context(project_config_path)
    validation = validate_project_mainflow(
        project_config_path=project_config_path,
        start_node=start_node,
        end_node=end_node,
    )
    target_nodes = list(validation.get("target_nodes") or [])
    if not target_nodes:
        raise ValueError("主链切片结果为空，无法运行项目主链")

    workspace_root = Path(str(context["workspace_root"]))
    bootstrap_runtime(str(workspace_root))

    task = create_task(
        title=f"{context['project_name']}主链运行",
        goal_text=str(context.get("project_goal") or "项目主链运行"),
        current_node_uid=target_nodes[0],
    )
    task_uid = str(task.get("task_uid") or task.get("uid_任务") or "")
    task_store.update_task_metadata(
        task_uid,
        {
            "runner_type": "project_mainflow",
            "project_config_path": str(context["project_config_path"]),
            "workspace_root": str(workspace_root),
            "decision_department_uid": decision_department_uid,
            "target_nodes": target_nodes,
        },
    )
    task_store.update_task_status(task_uid, TaskStatus.RUNNING)
    log_store.append_runtime_event(
        "项目主链开始",
        {
            "task_uid": task_uid,
            "project_name": context["project_name"],
            "project_config_path": str(context["project_config_path"]),
            "start_node": target_nodes[0],
            "end_node": target_nodes[-1],
            "simulate": bool(simulate),
            "decision_department_uid": decision_department_uid,
        },
    )

    events: list[dict[str, Any]] = []
    final_status = "completed"
    for node_code in target_nodes:
        try:
            request = create_task_request_from_project_node(
                project_config_path=str(context["project_config_path"]),
                node_code=node_code,
                task_uid=task_uid,
                source=source,
                metadata={
                    "runner_type": "project_mainflow",
                    "decision_department_uid": decision_department_uid,
                },
            )
        except Exception as exc:
            final_status = "blocked"
            task_store.update_task_status(task_uid, TaskStatus.BLOCKED)
            blocked_event = {
                "status": "blocked",
                "task_uid": task_uid,
                "node_code": node_code,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            events.append(blocked_event)
            log_store.append_blocked_event("项目主链阻断", blocked_event)
            break

        record = context["records"].get(node_code) or {}
        if not bool(record.get("implemented", False)):
            final_status = "blocked"
            blocked_result = {
                "task_uid": task_uid,
                "request_uid": str(request.get("request_uid") or ""),
                "node_code": node_code,
                "affair_uid": str(record.get("affair_uid") or request.get("target_affair_uid") or ""),
                "reason": "implemented_false",
            }
            _mark_request_blocked(str(request.get("request_uid") or ""), result=blocked_result)
            task_store.update_task_status(task_uid, TaskStatus.BLOCKED)
            events.append({"status": "blocked", **blocked_result})
            log_store.append_blocked_event("事务请求阻断", blocked_result)
            break

        event = run_task_request(str(request.get("request_uid") or ""), simulate=simulate)
        events.append(event)
        if event.get("status") == "failed":
            final_status = "failed"
            break
        if event.get("status") == "blocked":
            final_status = "blocked"
            break

    if final_status == "completed":
        task_store.mark_task_completed(task_uid)
    elif final_status == "failed":
        task_store.mark_task_failed(task_uid)
    elif final_status == "blocked":
        task_store.update_task_status(task_uid, TaskStatus.BLOCKED)

    payload = {
        "status": final_status,
        "task_uid": task_uid,
        "project_name": context["project_name"],
        "project_goal": context["project_goal"],
        "project_config_path": str(context["project_config_path"]),
        "workspace_root": str(workspace_root),
        "decision_department_uid": decision_department_uid,
        "simulate": bool(simulate),
        "validate": validation,
        "events": events,
        "task": task_store.get_task(task_uid),
        "requests": list_task_requests(task_uid=task_uid),
    }
    log_store.append_runtime_event("项目主链结束", payload)
    return payload


def get_decision_department(department_uid: str = "dept-default") -> Dict[str, Any]:
    """读取决策部门。"""

    return _get_department(department_uid)


def list_decision_departments() -> List[Dict[str, Any]]:
    """列出决策部门。"""

    return _list_departments()


def list_decision_department_members(department_uid: str = "dept-default") -> List[Dict[str, Any]]:
    """列出决策部门成员。"""

    return _list_department_members(department_uid)


def run_task_step(task_uid: str, graph_uid: str) -> DecisionResult:
    """公开的单步运行入口。"""

    graph = graph_registry.get_graph(graph_uid)
    return _run_task_step(task_uid=task_uid, graph=graph, run_uid=f"run-{task_uid}")


def run_task_until_wait(task_uid: str, graph_uid: str, max_steps: int = 100) -> list[DecisionResult]:
    """公开的持续运行入口。"""

    graph = graph_registry.get_graph(graph_uid)
    return _run_task_until_wait(task_uid=task_uid, graph=graph, max_steps=max_steps)


def run_task_until_terminal(task_uid: str, graph_uid: str, max_steps: int = 100) -> list[DecisionResult]:
    """公开的终止态运行入口。"""

    graph = graph_registry.get_graph(graph_uid)
    return _run_task_until_terminal(task_uid=task_uid, graph=graph, max_steps=max_steps)


def get_task_full_chain_view(task_uid: str) -> Dict[str, Any]:
    """返回任务全链路审计视图。

    Args:
        task_uid: 任务 UID。

    Returns:
        任务全链路审计视图。
    """

    return _build_task_full_chain_view(task_uid)


def get_decision_department_view(task_uid: str | None = None, decision_uid: str | None = None) -> Dict[str, Any]:
    """返回决策部门行为视图。

    Args:
        task_uid: 任务 UID，可选。
        decision_uid: 决策 UID，可选。

    Returns:
        决策部门行为视图。
    """

    return _build_decision_department_view(task_uid=task_uid, decision_uid=decision_uid)


def get_blocked_governance_view(task_uid: str | None = None) -> Dict[str, Any]:
    """返回阻断治理视图。

    Args:
        task_uid: 任务 UID，可选。

    Returns:
        阻断治理聚合视图。
    """

    return _build_blocked_governance_view(task_uid=task_uid)


def refresh_affair_registry(workspace_root: str | None = None, strict: bool = False) -> Dict[str, Any]:
    """刷新事务数据库并返回同步摘要。

    Args:
        workspace_root: 用户工作区根目录；为空时仅刷新官方库。
        strict: 严格模式，错误即抛异常。

    Returns:
        同步结果摘要。

    Examples:
        >>> result = refresh_affair_registry(workspace_root=None, strict=False)
        >>> isinstance(result.get("stats"), dict)
        True
    """

    resolved_workspace = resolve_portable_path(workspace_root, base_dir=Path.cwd()) if workspace_root else None
    result = sync_affair_databases(workspace_root=resolved_workspace, strict=strict)
    return {
        "schema_version": SCHEMA_VERSION,
        "aok_db_path": str(result.aok_db_path),
        "user_db_path": str(result.user_db_path) if str(result.user_db_path) else "",
        "record_count": len(result.records),
        "stats": dict(result.stats),
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }


def list_runtime_affairs(workspace_root: str | None = None, strict: bool = False) -> List[Dict[str, Any]]:
    """列出运行时可用事务记录。

    Args:
        workspace_root: 用户工作区根目录；为空时仅官方事务。
        strict: 严格模式开关。

    Returns:
        事务记录列表。

    Examples:
        >>> items = list_runtime_affairs(workspace_root=None, strict=False)
        >>> isinstance(items, list)
        True
    """

    resolved_workspace = resolve_portable_path(workspace_root, base_dir=Path.cwd()) if workspace_root else None
    registry = build_runtime_registry(workspace_root=resolved_workspace, strict=strict)
    return [dict(item) for item in registry.values()]


def check_affair_conflicts(workspace_root: str | None = None) -> Dict[str, Any]:
    """检查事务同步冲突与告警信息。

    Args:
        workspace_root: 用户工作区根目录；为空时仅检查官方库。

    Returns:
        冲突检查报告。

    Examples:
        >>> report = check_affair_conflicts(workspace_root=None)
        >>> "errors" in report
        True
    """

    resolved_workspace = resolve_portable_path(workspace_root, base_dir=Path.cwd()) if workspace_root else None
    result = sync_affair_databases(workspace_root=resolved_workspace, strict=False)
    return {
        "error_count": len(result.errors),
        "warning_count": len(result.warnings),
        "errors": list(result.errors),
        "warnings": list(result.warnings),
        "stats": dict(result.stats),
    }


def get_runtime_store_paths(base_dir: str | Path | None = None) -> Dict[str, str]:
    """返回当前运行时数据库目录与文件路径。

    Args:
        base_dir: 可选运行时根目录；为空时读取当前进程已初始化的运行时根目录。

    Returns:
        包含目录与文件绝对路径的字典。
    """

    dirs = {key: str(value) for key, value in get_runtime_store_dirs(base_dir=base_dir).items()}
    files = {key: str(value) for key, value in get_runtime_store_files(base_dir=base_dir).items()}
    return {
        "runtime_base_dir": dirs["runtime_base_dir"],
        "taskdb_dir": dirs["taskdb"],
        "logdb_dir": dirs["logdb"],
        "decisiondb_dir": dirs["decisiondb"],
        "graph_registry_dir": dirs["graph_registry"],
        "tasks_file": files["tasks"],
        "task_relations_file": files["task_relations"],
        "task_steps_file": files["task_steps"],
        "snapshots_file": files["snapshots"],
        "runtime_events_file": files["runtime_events"],
        "decisions_file": files["decisions"],
        "graphs_file": files["graphs"],
        "types_file": files["types"],
    }


def get_affair_registry_paths(workspace_root: str | Path | None = None) -> Dict[str, str]:
    """返回事务管理系统相关路径。

    Args:
        workspace_root: 用户工作区根目录；为空时仅返回官方路径。

    Returns:
        路径字典。
    """

    resolved_workspace = _normalize_workspace_root(workspace_root) if workspace_root is not None else None
    return {key: str(value) for key, value in _get_affair_registry_paths(resolved_workspace).items()}


def list_tools() -> List[str]:
    """返回可用工具名称列表。

    Returns:
        已导出的工具函数名列表。
    """

    tools_module = _load_tools_module()
    exported = getattr(tools_module, "__all__", [])
    if isinstance(exported, list):
        return [str(item) for item in exported]
    return []


def get_tool(tool_name: str) -> Any:
    """按名称获取工具函数。

    Args:
        tool_name: 工具函数名。

    Returns:
        可调用工具函数。

    Raises:
        KeyError: 当工具不存在时抛出。
    """

    key = str(tool_name or "").strip()
    if not key:
        raise KeyError("tool_name 不能为空")

    tools_module = _load_tools_module()
    if not hasattr(tools_module, key):
        raise KeyError(f"工具不存在：{key}")
    return getattr(tools_module, key)


def list_public_tools(exposure: str | None = None, kind: str | None = None) -> List[Dict[str, Any]]:
    """列出 AOK 公开工具（函数名模式）。

    Args:
        exposure: 兼容旧参数。`public-read/public-safe` 映射到 user，`internal` 映射到 developer。
        kind: 兼容旧参数，当前未使用。

    Returns:
        list[dict[str, Any]]: 工具条目列表。

    Raises:
        KeyError: 当工具模块未提供工具清单接口时抛出。
    """

    _ = kind
    tools_module = _load_tools_module()
    list_user = getattr(tools_module, "list_user_tools", None)
    list_developer = getattr(tools_module, "list_developer_tools", None)
    if list_user is None or list_developer is None:
        raise KeyError("工具模块未提供 list_user_tools/list_developer_tools 接口")

    if exposure == "internal":
        scope = "developer"
    elif exposure in {"public-read", "public-safe"}:
        scope = "user"
    else:
        scope = "all"

    rows: list[dict[str, Any]] = []
    if scope in {"user", "all"}:
        for name in list_user():
            rows.append({"tool_name": str(name), "scope": "user"})
    if scope in {"developer", "all"}:
        for name in list_developer():
            rows.append({"tool_name": str(name), "scope": "developer"})
    return rows


def list_capabilities(include_internal: bool = False) -> List[Dict[str, Any]]:
    """列出 public capability 摘要。

    Args:
        include_internal: 是否包含 developer/internal 能力。

    Returns:
        capability 摘要列表。
    """

    tools_module = _load_tools_module_with_attrs("list_capabilities")
    list_capabilities_fn = getattr(tools_module, "list_capabilities")
    return list_capabilities_fn(include_internal=include_internal)


def lint_capabilities() -> Dict[str, Any]:
    """校验 capability manifest/schema/实现一致性。

    Returns:
        lint 摘要字典。
    """

    tools_module = _load_tools_module_with_attrs("lint_public_manifest")
    lint_fn = getattr(tools_module, "lint_public_manifest")
    return lint_fn()


def invoke_capability(
    capability_id: str,
    *,
    payload: Dict[str, Any] | None = None,
    caller_context: Dict[str, Any] | None = None,
    allow_internal: bool = False,
    workspace_root: str | Path | None = None,
) -> Dict[str, Any]:
    """统一执行 public capability。

    Args:
        capability_id: 能力标识。
        payload: 输入参数。
        caller_context: 调用上下文。
        allow_internal: 是否允许 developer/internal 能力。
        workspace_root: 工作区根目录，用于审计落盘。

    Returns:
        统一协议结果字典。
    """

    tools_module = _load_tools_module_with_attrs("invoke_capability")
    invoke_fn = getattr(tools_module, "invoke_capability")
    return invoke_fn(
        capability_id,
        payload=payload,
        caller_context=caller_context,
        allow_internal=allow_internal,
        workspace_root=workspace_root,
    )


def invoke_public_tool(
    capability_id: str,
    *,
    payload: Any | None = None,
    caller_context: Dict[str, Any] | None = None,
    allow_internal: bool = False,
) -> Dict[str, Any]:
    """调用 AOK 公开工具（兼容旧接口名）。

    Args:
        capability_id: 工具函数名（兼容旧字段名）。
        payload: 调用参数；支持 `{"args": [...], "kwargs": {...}}`，也兼容直接字典 kwargs。
        caller_context: 调用方上下文，当前仅用于记录来源。
        allow_internal: 兼容旧参数；当前通过 scope 控制是否允许开发者工具。

    Returns:
        dict[str, Any]: 调用结果。

    Raises:
        KeyError: 当工具模块未提供工具调用接口时抛出。
    """

    target = str(capability_id or "").strip()
    if not target:
        raise ValueError("capability_id 不能为空")

    context = dict(caller_context or {})
    context.setdefault("caller_source", "autodoengine.api")

    if payload is None:
        normalized_payload: dict[str, Any] = {}
    elif isinstance(payload, dict):
        raw_args = payload.get("args", None)
        raw_kwargs = payload.get("kwargs", None)
        if raw_args is None and raw_kwargs is None:
            normalized_payload = dict(payload)
        else:
            if raw_args:
                raise ValueError("invoke_public_tool 已切换到 capability 模式，不再支持 args")
            normalized_payload = dict(raw_kwargs or {})
    else:
        raise ValueError("invoke_public_tool 的 payload 必须是对象")

    return invoke_capability(
        target,
        payload=normalized_payload,
        caller_context=context,
        allow_internal=allow_internal,
        workspace_root=normalized_payload.get("workspace_root"),
    )


def prepare_affair_config(*, config: Dict[str, Any], workspace_root: str | Path) -> Dict[str, Any]:
    """预处理事务配置路径。

    Args:
        config: 原始配置字典。
        workspace_root: 工作区根目录。

    Returns:
        路径已绝对化后的配置字典。
    """

    workspace = _normalize_workspace_root(workspace_root)
    normalized = dict(config or {})
    normalized.setdefault("_workspace_root", str(workspace))

    try:
        aok_module = importlib.import_module("autodokit")
        aok_prepare_affair_config = getattr(aok_module, "prepare_affair_config", None)
        if callable(aok_prepare_affair_config):
            resolved = dict(aok_prepare_affair_config(config=normalized, workspace_root=workspace))
            resolved.setdefault(
                "_path_preprocess_summary",
                {
                    "processor": "autodokit.prepare_affair_config",
                    "workspace_root": str(workspace),
                },
            )
            return resolved
    except Exception:
        pass

    resolved, audit = resolve_paths_to_absolute_with_audit(normalized, workspace_root=workspace)
    resolved["_path_preprocess_summary"] = audit
    return resolved


def import_affair_module(affair_uid: str, *, workspace_root: str | Path | None = None, strict: bool = False) -> Any:
    """按事务 UID 导入事务模块。

    Args:
        affair_uid: 事务 UID。
        workspace_root: 工作区根目录。
        strict: 严格模式。

    Returns:
        已导入的 Python 模块对象。
    """

    workspace = _normalize_workspace_root(workspace_root)
    registry = build_registry(strict=strict, workspace_root=workspace)
    runner = resolve_runner(affair_uid, registry)
    module_name = str(runner.get("module") or "").strip()
    source_py_path = str(runner.get("source_py_path") or "").strip()
    if module_name:
        return importlib.import_module(module_name)
    if source_py_path:
        return _load_module_from_file(source_py_path)
    raise ValueError(f"事务[{affair_uid}] 缺少可导入入口（runner.module/source_py_path）")


def import_user_affair(
    *,
    source_py_path: str | Path,
    workspace_root: str | Path,
    source_params_json_path: str | Path | None = None,
    source_doc_md_path: str | Path | None = None,
    affair_name: str | None = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """导入用户功能程序为事务三件套并注册到事务管理系统。

    Args:
        source_py_path: 功能程序文件路径。
        workspace_root: 用户工作区根目录。
        source_params_json_path: 参数模板 JSON 路径，可选。
        source_doc_md_path: 说明文档 MD 路径，可选。
        affair_name: 事务名称，可选。
        strict: 严格模式，数据库同步有错误时抛异常。

    Returns:
        导入摘要字典。
    """

    workspace = _normalize_workspace_root(workspace_root)
    result = _import_user_affair(
        workspace_root=workspace,
        source_py_path=resolve_portable_path(str(source_py_path), base_dir=workspace),
        source_params_json_path=(
            resolve_portable_path(str(source_params_json_path), base_dir=workspace)
            if source_params_json_path is not None
            else None
        ),
        source_doc_md_path=(
            resolve_portable_path(str(source_doc_md_path), base_dir=workspace)
            if source_doc_md_path is not None
            else None
        ),
        affair_name=affair_name,
        strict=strict,
    )

    return {
        "requested_name": result.requested_name,
        "final_name": result.final_name,
        "affair_uid": result.affair_uid,
        "renamed": result.renamed,
        "affair_dir": str(result.affair_dir),
        "source_py_path": str(result.source_py_path),
        "params_json_path": str(result.params_json_path),
        "doc_md_path": str(result.doc_md_path),
        "collision_history": list(result.collision_history),
        "warnings": list(result.warnings),
    }


def run_affair(
    affair_uid: str,
    *,
    config: Dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    workspace_root: str | Path | None = None,
    strict: bool = False,
    runner_kwargs: Dict[str, Any] | None = None,
) -> List[Path]:
    """统一事务直调入口（强制经由事务管理系统）。

    Args:
        affair_uid: 事务 UID。
        config: 字典配置（`config_dict` 模式优先）。
        config_path: 配置文件路径（JSON/PY）。
        workspace_root: 工作区根目录。
        strict: 严格模式，存在注册错误时抛异常。
        runner_kwargs: 追加给 runner 的调用参数。

    Returns:
        事务产物路径列表。

    Raises:
        ValueError: 参数非法时抛出。
        KeyError: 事务不存在时抛出。
    """

    uid = str(affair_uid or "").strip()
    if not uid:
        raise ValueError("affair_uid 不能为空")

    workspace = _normalize_workspace_root(workspace_root)
    registry = build_registry(strict=strict, workspace_root=workspace)
    runner = resolve_runner(uid, registry)

    module_name = str(runner.get("module") or "").strip()
    source_py_path = str(runner.get("source_py_path") or "").strip()
    if module_name:
        module = importlib.import_module(module_name)
    elif source_py_path:
        module = _load_module_from_file(source_py_path)
    else:
        raise ValueError(f"事务[{uid}] 缺少可导入入口（runner.module/source_py_path）")
    callable_obj = getattr(module, str(runner["callable"]))

    merged_kwargs: Dict[str, Any] = {}
    if isinstance(runner.get("kwargs"), dict):
        merged_kwargs.update(dict(runner.get("kwargs") or {}))
    if isinstance(runner_kwargs, dict):
        merged_kwargs.update(runner_kwargs)

    pass_mode = str(runner["pass_mode"])

    if pass_mode == "config_dict":
        config_dict: Dict[str, Any]
        if config is not None:
            config_dict = dict(config)
        elif config_path is not None:
            path_obj = resolve_portable_path(str(config_path), base_dir=workspace)
            config_dict = load_json_or_py(path_obj)
        else:
            config_dict = {}

        final_config = prepare_affair_config(config=config_dict, workspace_root=workspace)
        if config_path is not None:
            resolved_config_path = resolve_portable_path(str(config_path), base_dir=workspace)
        else:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
                json.dump(final_config, fp, ensure_ascii=False, indent=2)
                resolved_config_path = Path(fp.name)

        try:
            with _runtime_context_scope(workspace_root=workspace, affair_uid=uid, config_path=resolved_config_path):
                result = callable_obj(final_config, **merged_kwargs)
        finally:
            if config_path is None and resolved_config_path.exists():
                resolved_config_path.unlink(missing_ok=True)
        return _normalize_affair_outputs(result)

    if pass_mode == "config_path":
        if config_path is not None:
            raw_config_path = resolve_portable_path(str(config_path), base_dir=workspace)
            raw_config = load_json_or_py(raw_config_path)
            final_config = prepare_affair_config(config=raw_config, workspace_root=workspace)
        elif config is not None:
            final_config = prepare_affair_config(config=dict(config), workspace_root=workspace)
        else:
            final_config = prepare_affair_config(config={}, workspace_root=workspace)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
            json.dump(final_config, fp, ensure_ascii=False, indent=2)
            resolved_config_path = Path(fp.name)

        try:
            with _runtime_context_scope(workspace_root=workspace, affair_uid=uid, config_path=resolved_config_path):
                result = callable_obj(str(resolved_config_path), **merged_kwargs)
        finally:
            resolved_config_path.unlink(missing_ok=True)
        return _normalize_affair_outputs(result)

    raise ValueError(f"不支持的 pass_mode：{pass_mode}")

