"""静态图模型定义。

本模块并存两套节点表示：

- **运行态精简模型**（`Graph`/`GraphNode`/`GraphEdge`）：由 `graph_loader` 构建，
  供实时主链（`api` / 调度 / 运行时）消费。
- **V2 流程图前端模型**（`Node`/`Edge`/`NodePort`/`NodeContent`/`NodeContentV2`）：
  带端口与内容契约，供 AOF→FlowGraph→compiler 编译链消费
  （`workflow`/`compiler`/`templates`/`aof` 依赖）。二者统一脊柱前并存。

`FlowGraphError` 为前端建模/编译过程中的通用错误。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class FlowGraphError(Exception):
    """流程图建模、校验或编译过程中的通用错误。"""


@dataclass(slots=True)
class GraphPolicy:
    """图策略对象。"""

    values: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphContainer:
    """图容器对象。"""

    container_id: str
    container_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphNode:
    """静态图节点对象。"""

    node_uid: str
    node_type: str
    affair_uid: str | None
    container_id: str | None
    risk_level: str = "normal"
    policies: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(slots=True)
class GraphEdge:
    """静态图边对象。"""

    edge_uid: str
    from_node_uid: str
    to_node_uid: str
    base_tendency_score: float = 1.0
    condition_expr: str | None = None
    enabled: bool = True
    version: str | None = None


@dataclass(slots=True)
class Graph:
    """静态图对象。"""

    graph_uid: str
    graph_name: str
    graph_version: str
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    containers: dict[str, GraphContainer] = field(default_factory=dict)
    policies: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# V2 流程图前端模型（AOF→FlowGraph→compiler 编译链使用）
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NodePort:
    """节点端口定义（编译链声明输入/输出端口，暂不承载数据传递）。"""

    name: str
    data_type: str = "any"


@dataclass(slots=True)
class NodeContentV2:
    """节点内容契约的 V2 扁平表示。"""

    content_kind: str
    content_ref: str
    content_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NodeContent:
    """节点内容（统一 `content_kind`/`content_ref`/`content_payload` 契约）。"""

    content_kind: str
    content_ref: str
    content_payload: dict[str, Any] = field(default_factory=dict)

    def to_v2(self) -> NodeContentV2:
        """导出为扁平 V2 表示。"""

        return NodeContentV2(
            content_kind=self.content_kind,
            content_ref=self.content_ref,
            content_payload=dict(self.content_payload or {}),
        )

    @classmethod
    def from_v2(cls, content_v2: NodeContentV2) -> "NodeContent":
        """由 V2 扁平表示构造。"""

        return cls(
            content_kind=content_v2.content_kind,
            content_ref=content_v2.content_ref,
            content_payload=dict(content_v2.content_payload or {}),
        )

    @classmethod
    def from_mapping(cls, mapping: Any, *, node_uid: str = "") -> "NodeContent":
        """从字典构造并校验内容契约。

        Args:
            mapping: 含 `content_kind`/`content_ref`/`content_payload` 的映射。
            node_uid: 出错信息中引用的节点 uid。

        Returns:
            校验通过的 `NodeContent`。

        Raises:
            FlowGraphError: 内容类型非法、引用为空或载荷结构错误。
        """

        data = dict(mapping or {})
        content_kind = str(data.get("content_kind") or "").strip()
        content_ref = str(data.get("content_ref") or "").strip()
        if content_kind not in {"affair", "subgraph"}:
            raise FlowGraphError(
                f"节点[{node_uid}] content_kind 非法（仅支持 affair/subgraph）：{content_kind!r}"
            )
        if not content_ref:
            raise FlowGraphError(f"节点[{node_uid}] content_ref 不能为空")
        payload = data.get("content_payload") or {}
        if not isinstance(payload, dict):
            raise FlowGraphError(f"节点[{node_uid}] content_payload 必须是对象")
        return cls(content_kind=content_kind, content_ref=content_ref, content_payload=dict(payload))


@dataclass(slots=True)
class Node:
    """V2 流程图节点（容器，承载内容契约与端口）。"""

    uid: str
    node_type: str
    content: NodeContent
    is_leaf: bool = False
    is_business_node: bool = True
    is_graph_node: bool = False
    graph_meta: dict[str, Any] = field(default_factory=dict)
    allow_multi_input_ports: list[str] = field(default_factory=list)
    input_ports: dict[str, NodePort] = field(default_factory=dict)
    output_ports: dict[str, NodePort] = field(default_factory=dict)

    @property
    def content_v2(self) -> NodeContentV2:
        """节点内容的 V2 扁平表示。"""

        return self.content.to_v2()


@dataclass(slots=True)
class Edge:
    """V2 流程图有向连线（端口到端口，携带条件标签）。"""

    uid: str
    source_node_uid: str
    source_port_name: str
    target_node_uid: str
    target_port_name: str
    condition_label: str | None = None
    graph_meta: dict[str, Any] = field(default_factory=dict)
