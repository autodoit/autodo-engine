"""v4 对外公开 API。"""

from __future__ import annotations

import importlib
import importlib.util
import json
import tempfile
from hashlib import sha256
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from autodoengine.core.types import DecisionResult
from autodoengine.flow_graph import load_graph_from_file
from autodoengine.flow_graph.models import Graph
from autodoengine.scheduling.task_loop import run_task_step as _run_task_step
from autodoengine.scheduling.task_loop import run_task_until_terminal as _run_task_until_terminal
from autodoengine.scheduling.task_loop import run_task_until_wait as _run_task_until_wait
from autodoengine.taskdb import bootstrap_runtime_storage
from autodoengine.taskdb import graph_registry, task_store
from autodoengine.taskdb import (
    build_blocked_governance_view as _build_blocked_governance_view,
    build_decision_department_view as _build_decision_department_view,
    build_task_full_chain_view as _build_task_full_chain_view,
)
from autodoengine.taskdb.storage_paths import get_runtime_store_dirs, get_runtime_store_files
from autodoengine.utils.affair_registry import build_registry, resolve_runner
from autodoengine.utils.common.affair_manager import import_user_affair as _import_user_affair
from autodoengine.utils.common.affair_sync import SCHEMA_VERSION, build_runtime_registry, get_affair_registry_paths as _get_affair_registry_paths, sync_affair_databases
from autodoengine.utils.path_tools import load_json_or_py, resolve_paths_to_absolute


def _load_autodokit_tools_module() -> Any:
    """按需加载 autodo-kit 工具模块。

    Returns:
        `autodokit.tools` 模块对象。

    Raises:
        ModuleNotFoundError: 当未安装 autodo-kit 时抛出更明确的错误。
    """

    try:
        return importlib.import_module("autodokit.tools")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "未找到 autodokit.tools。请先安装 autodo-kit，再使用工具查询或事务直调接口。"
        ) from exc


def _normalize_workspace_root(workspace_root: str | Path | None) -> Path:
    """规范化工作区根目录。

    Args:
        workspace_root: 工作区根目录。

    Returns:
        绝对路径形式的工作区根目录。
    """

    if workspace_root is None:
        return Path.cwd().resolve()
    return Path(workspace_root).resolve()


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

    source_path = Path(source_py_path).resolve()
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

    target = Path(file_path).resolve()
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

    resolved_workspace = Path(workspace_root).resolve() if workspace_root else None
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

    resolved_workspace = Path(workspace_root).resolve() if workspace_root else None
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

    resolved_workspace = Path(workspace_root).resolve() if workspace_root else None
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

    tools_module = _load_autodokit_tools_module()
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

    tools_module = _load_autodokit_tools_module()
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
        KeyError: 当 `autodokit.tools` 未提供工具清单接口时抛出。
    """

    _ = kind
    tools_module = _load_autodokit_tools_module()
    list_user = getattr(tools_module, "list_user_tools", None)
    list_developer = getattr(tools_module, "list_developer_tools", None)
    if list_user is None or list_developer is None:
        raise KeyError("autodokit.tools 未提供 list_user_tools/list_developer_tools 接口")

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
        KeyError: 当 `autodokit.tools` 未提供工具调用接口时抛出。
    """

    target = str(capability_id or "").strip()
    if not target:
        raise ValueError("capability_id 不能为空")

    tools_module = _load_autodokit_tools_module()
    get_tool = getattr(tools_module, "get_tool", None)
    if get_tool is None:
        raise KeyError("autodokit.tools 未提供 get_tool 接口")

    context = dict(caller_context or {})
    context.setdefault("caller_source", "autodoengine.api")
    scope = "all" if allow_internal else "user"

    call_args: list[Any]
    call_kwargs: dict[str, Any]
    if payload is None:
        call_args = []
        call_kwargs = {}
    elif isinstance(payload, dict):
        raw_args = payload.get("args", None)
        raw_kwargs = payload.get("kwargs", None)
        if raw_args is None and raw_kwargs is None:
            call_args = []
            call_kwargs = dict(payload)
        else:
            call_args = list(raw_args or [])
            call_kwargs = dict(raw_kwargs or {})
    else:
        call_args = [payload]
        call_kwargs = {}

    tool_fn = get_tool(target, scope=scope)
    result = tool_fn(*call_args, **call_kwargs)
    return {
        "status": "success",
        "tool_name": target,
        "caller": context,
        "data": result,
    }


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
    return resolve_paths_to_absolute(normalized, workspace_root=workspace)


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

    result = _import_user_affair(
        workspace_root=Path(workspace_root).resolve(),
        source_py_path=Path(source_py_path).resolve(),
        source_params_json_path=Path(source_params_json_path).resolve() if source_params_json_path is not None else None,
        source_doc_md_path=Path(source_doc_md_path).resolve() if source_doc_md_path is not None else None,
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
            path_obj = Path(config_path).resolve()
            config_dict = load_json_or_py(path_obj)
        else:
            config_dict = {}

        final_config = prepare_affair_config(config=config_dict, workspace_root=workspace)
        result = callable_obj(final_config, **merged_kwargs)
        return _normalize_affair_outputs(result)

    if pass_mode == "config_path":
        if config_path is not None:
            resolved_config_path = Path(config_path).resolve()
        elif config is not None:
            final_config = prepare_affair_config(config=dict(config), workspace_root=workspace)
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
                json.dump(final_config, fp, ensure_ascii=False, indent=2)
                resolved_config_path = Path(fp.name)
        else:
            final_config = prepare_affair_config(config={}, workspace_root=workspace)
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
                json.dump(final_config, fp, ensure_ascii=False, indent=2)
                resolved_config_path = Path(fp.name)

        result = callable_obj(str(resolved_config_path), **merged_kwargs)
        return _normalize_affair_outputs(result)

    raise ValueError(f"不支持的 pass_mode：{pass_mode}")

