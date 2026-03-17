"""流程图编译器：FlowGraph -> workflow.json。

本模块把流程图（DAG）编译为现有调度器可执行的 `workflow.json` 结构。

输出结构：
- `affairs`: 以“节点 uid”为 key 的事务配置对象（确保同一事务可多次实例化）
- `flow`: 串行执行列表（拓扑排序后扁平化）
- `flow_groups`: 并行分组列表（按层级拓扑分层，组内可并行）

注意：
- 目前并不做“端口数据传递”的自动注入，连线仅用于表达依赖关系。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .models import FlowGraphError, Node
from .workflow import FlowGraph
from .templates import NodeTemplate


def _extract_container_path(node: Node) -> List[str]:
    """提取节点容器路径。

    Args:
        node: 流程图节点。

    Returns:
        节点所在容器路径（由外层到内层）。
    """

    graph_meta = node.graph_meta if isinstance(node.graph_meta, dict) else {}
    aof_meta = graph_meta.get("aof") if isinstance(graph_meta.get("aof"), dict) else {}
    raw_path = aof_meta.get("container_path")
    if not isinstance(raw_path, list):
        return []
    return [str(item).strip() for item in raw_path if str(item).strip()]


def _build_containers(graph: FlowGraph) -> List[Dict[str, Any]]:
    """基于节点容器路径构建 V2 容器列表。

    Args:
        graph: 流程图对象。

    Returns:
        V2 `containers` 列表，包含 `root`。
    """

    containers: Dict[str, Dict[str, Any]] = {"root": {"id": "root", "parent": "", "policies": {}}}

    for node in graph.nodes.values():
        path = _extract_container_path(node)
        parent = "root"
        for container_id in path:
            if container_id not in containers:
                containers[container_id] = {
                    "id": container_id,
                    "parent": parent,
                    "policies": {},
                }
            parent = container_id

    return list(containers.values())


def _build_nodes_v2(graph: FlowGraph) -> List[Dict[str, Any]]:
    """构建 V2 节点列表。

    Args:
        graph: 流程图对象。

    Returns:
        V2 `nodes` 列表。
    """

    nodes: List[Dict[str, Any]] = []
    for uid, node in graph.nodes.items():
        content_v2 = node.content_v2
        path = _extract_container_path(node)
        container = path[-1] if path else "root"
        nodes.append(
            {
                "id": uid,
                "uid": uid,
                "node_type": node.node_type,
                "container": container,
                "content": {
                    "content_kind": content_v2.content_kind,
                    "content_ref": content_v2.content_ref,
                    "content_payload": dict(content_v2.content_payload or {}),
                },
                "ports": {
                    "inputs": {
                        key: {"name": port.name, "data_type": port.data_type}
                        for key, port in (node.input_ports or {}).items()
                    },
                    "outputs": {
                        key: {"name": port.name, "data_type": port.data_type}
                        for key, port in (node.output_ports or {}).items()
                    },
                },
                "policies": {},
            }
        )
    return nodes


def _build_edges_v2(graph: FlowGraph) -> List[Dict[str, Any]]:
    """构建 V2 连线列表。

    Args:
        graph: 流程图对象。

    Returns:
        V2 `edges` 列表。
    """

    edges: List[Dict[str, Any]] = []
    for edge in graph.edges.values():
        edges.append(
            {
                "uid": edge.uid,
                "source_node_uid": edge.source_node_uid,
                "target_node_uid": edge.target_node_uid,
                "condition_label": edge.condition_label,
            }
        )
    return edges


def _topological_layers(graph: FlowGraph) -> List[List[str]]:
    """将 DAG 分解为拓扑层（Kahn 分层）。

    Args:
        graph: 流程图对象。

    Returns:
        分层后的节点 uid 列表，外层列表为层，内层为同层节点。

    Raises:
        FlowGraphError: 检测到环或包含未知节点。
    """

    node_uids = list(graph.nodes.keys())
    indegree: Dict[str, int] = {uid: 0 for uid in node_uids}
    outgoing: Dict[str, List[str]] = {uid: [] for uid in node_uids}

    for edge in graph.edges.values():
        if edge.source_node_uid not in indegree or edge.target_node_uid not in indegree:
            raise FlowGraphError("连线引用了不存在的节点，无法编译。")
        indegree[edge.target_node_uid] += 1
        outgoing[edge.source_node_uid].append(edge.target_node_uid)

    remaining = set(node_uids)
    layers: List[List[str]] = []

    while remaining:
        current = sorted([uid for uid in remaining if indegree[uid] == 0])
        if not current:
            raise FlowGraphError("流程图存在环（cycle），无法拓扑排序编译为工作流。")
        layers.append(current)
        for uid in current:
            remaining.remove(uid)
            for nxt in outgoing.get(uid, []):
                indegree[nxt] -= 1

    return layers


def _merge_affair_cfg(base: Dict[str, Any], payload: Mapping[str, Any]) -> Dict[str, Any]:
    """合并事务基础配置与节点 payload。

    规则：
    - payload 默认合并进 `config`（内联配置）字段；
    - 若 base 没有 `config`，则创建空 dict 再合并。

    Args:
        base: 模板提供的基础 affair 配置。
        payload: 节点 payload。

    Returns:
        合并后的 affair 配置。
    """

    merged = dict(base)
    inline_cfg = merged.get("config")
    if not isinstance(inline_cfg, dict):
        inline_cfg = {}

    inline_cfg = dict(inline_cfg)
    inline_cfg.update(dict(payload))
    merged["config"] = inline_cfg
    return merged


def compile_flow_graph_to_workflow_dict(
    graph: FlowGraph,
    *,
    templates_by_content_ref: Mapping[str, NodeTemplate],
    workflow_id: str | None = None,
    workflow_name: str | None = None,
    emit_flow_groups: bool = True,
) -> Dict[str, Any]:
    """把流程图编译为 workflow.json 字典。

    Args:
        graph: 流程图对象。
        templates_by_content_ref: 按 `content_ref` 索引的节点模板映射。
        workflow_id: 输出 workflow_id（不提供则用 graph.uid）。
        workflow_name: 输出 workflow_name（可选）。
        emit_flow_groups: 是否输出 `flow_groups` 字段。

    Returns:
        可直接写入 JSON 的字典结构。

    Raises:
        FlowGraphError: 节点模板缺失或流程图非法。
    """

    layers = _topological_layers(graph)

    affairs: Dict[str, Any] = {}
    subgraph_refs: Dict[str, Any] = {}

    for node_uid, node in graph.nodes.items():
        content_v2 = node.content_v2

        if content_v2.content_kind == "affair":
            content_ref = content_v2.content_ref
            tmpl = templates_by_content_ref.get(content_ref)
            if tmpl is None:
                raise FlowGraphError(f"找不到事务节点模板：content_ref={content_ref}")

            # 使用 node_uid 作为 workflow.json 的事务 key，保证唯一。
            base_cfg = dict(tmpl.affair)

            base_cfg.setdefault("content_ref", content_ref)

            merged_cfg = _merge_affair_cfg(base_cfg, content_v2.content_payload)
            merged_cfg.setdefault("content_ref", content_ref)
            affairs[node_uid] = merged_cfg
            continue

        if content_v2.content_kind == "subgraph":
            subgraph_refs[node_uid] = {
                "content_ref": content_v2.content_ref,
                "content_payload": dict(content_v2.content_payload or {}),
            }
            continue

        raise FlowGraphError(f"不支持的节点内容类型：{content_v2.content_kind}（node={node_uid}）")

    flow_groups = [layer[:] for layer in layers]
    flow = [uid for layer in layers for uid in layer]

    out: Dict[str, Any] = {
        "workflow_id": workflow_id or graph.uid,
        "workflow_name": workflow_name or graph.uid,
        "schema_version": "node_runtime_v2",
        "affairs": affairs,
        "nodes": _build_nodes_v2(graph),
        "edges": _build_edges_v2(graph),
        "containers": _build_containers(graph),
        "flow": flow,
    }
    if subgraph_refs:
        out["subgraph_refs"] = subgraph_refs
    if emit_flow_groups:
        out["flow_groups"] = flow_groups

    return out


def write_workflow_json(workflow_dict: Dict[str, Any], path: str | Path) -> Path:
    """把 workflow 字典写入 JSON 文件。

    Args:
        workflow_dict: workflow.json 字典。
        path: 输出路径。

    Returns:
        写入后的绝对路径。
    """

    out_path = Path(path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(workflow_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
