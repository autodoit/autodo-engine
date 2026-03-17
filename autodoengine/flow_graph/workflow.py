"""流程图容器与基础操作。

本模块提供最简可复用能力：
- 注册节点
- 连接节点
- 基础合法性校验
- 字典化导入导出
"""

from __future__ import annotations

from typing import Any, Dict, List

from .models import Edge, Node, NodeContent, NodePort, FlowGraphError


class FlowGraph:
    """最简流程图。

    Attributes:
        uid: 工作流唯一标识。
        nodes: 节点集合，键为节点 uid。
        edges: 连线集合，键为连线 uid。

    Args:
        uid: 工作流唯一标识。

    Raises:
        FlowGraphError: 当工作流 uid 为空时抛出。

    Examples:
        >>> workflow = FlowGraph(uid="wf-1")
        >>> workflow.uid
        'wf-1'
    """

    def __init__(self, uid: str):
        """初始化工作流对象。

        Args:
            uid: 工作流唯一标识。

        Raises:
            FlowGraphError: 当工作流 uid 为空时抛出。
        """

        if not uid or not uid.strip():
            raise FlowGraphError("工作流 uid 不能为空。")
        self.uid = uid
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[str, Edge] = {}

    def add_node(self, node: Node) -> None:
        """添加节点。

        Args:
            node: 待添加节点。

        Raises:
            FlowGraphError: 当节点 uid 已存在时抛出。
        """

        if node.uid in self.nodes:
            raise FlowGraphError(f"节点 uid 已存在：{node.uid}")
        self.nodes[node.uid] = node

    def add_edge(self, edge: Edge) -> None:
        """添加有向连线并进行基础校验。

        校验规则：
        - 起点/终点节点必须存在；
        - 起点端口必须属于起点节点输出端口；
        - 终点端口必须属于终点节点输入端口；
        - 叶子节点不能作为连线起点；
        - 默认同一目标输入端口只允许一个上游连线；
        - 若端口在目标节点 `allow_multi_input_ports` 中，则允许多个上游。

        Args:
            edge: 待添加连线。

        Raises:
            FlowGraphError: 当连线不合法时抛出。
        """

        if edge.uid in self.edges:
            raise FlowGraphError(f"连线 uid 已存在：{edge.uid}")

        source_node = self.nodes.get(edge.source_node_uid)
        target_node = self.nodes.get(edge.target_node_uid)
        if source_node is None:
            raise FlowGraphError(f"起点节点不存在：{edge.source_node_uid}")
        if target_node is None:
            raise FlowGraphError(f"终点节点不存在：{edge.target_node_uid}")

        if source_node.is_leaf:
            raise FlowGraphError(f"叶子节点不能作为连线起点：{source_node.uid}")

        if edge.source_port_name not in source_node.output_ports:
            raise FlowGraphError(
                f"起点端口不存在：节点[{source_node.uid}] 无输出端口 [{edge.source_port_name}]"
            )
        if edge.target_port_name not in target_node.input_ports:
            raise FlowGraphError(
                f"终点端口不存在：节点[{target_node.uid}] 无输入端口 [{edge.target_port_name}]"
            )

        allow_multi_ports = set(target_node.allow_multi_input_ports or [])
        if edge.target_port_name not in allow_multi_ports:
            for existing_edge in self.edges.values():
                same_target = existing_edge.target_node_uid == edge.target_node_uid
                same_port = existing_edge.target_port_name == edge.target_port_name
                if same_target and same_port:
                    raise FlowGraphError(
                        "同一输入端口仅允许一个上游连线："
                        f"节点[{edge.target_node_uid}] 端口[{edge.target_port_name}]"
                    )

        self.edges[edge.uid] = edge

    def get_incoming_edges(self, node_uid: str) -> List[Edge]:
        """获取节点入连线列表。

        Args:
            node_uid: 节点 uid。

        Returns:
            指向该节点的所有连线。
        """

        return [edge for edge in self.edges.values() if edge.target_node_uid == node_uid]

    def get_outgoing_edges(self, node_uid: str) -> List[Edge]:
        """获取节点出连线列表。

        Args:
            node_uid: 节点 uid。

        Returns:
            从该节点发出的所有连线。
        """

        return [edge for edge in self.edges.values() if edge.source_node_uid == node_uid]

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典结构。

        默认输出节点 `content` 新结构：
        - `content_kind`
        - `content_ref`
        - `content_payload`

        Returns:
            可序列化字典。
        """

        nodes_payload: List[Dict[str, Any]] = []
        for node in self.nodes.values():
            content_v2 = node.content.to_v2()
            content_data: Dict[str, Any] = {
                "content_kind": content_v2.content_kind,
                "content_ref": content_v2.content_ref,
                "content_payload": dict(content_v2.content_payload or {}),
            }

            nodes_payload.append(
                {
                    "uid": node.uid,
                    "node_type": node.node_type,
                    "is_leaf": node.is_leaf,
                    "is_business_node": node.is_business_node,
                    "is_graph_node": node.is_graph_node,
                    "graph_meta": dict(node.graph_meta or {}),
                    "allow_multi_input_ports": list(node.allow_multi_input_ports or []),
                    "input_ports": {
                        key: {"name": port.name, "data_type": port.data_type}
                        for key, port in (node.input_ports or {}).items()
                    },
                    "output_ports": {
                        key: {"name": port.name, "data_type": port.data_type}
                        for key, port in (node.output_ports or {}).items()
                    },
                    "content": content_data,
                }
            )

        return {
            "uid": self.uid,
            "nodes": nodes_payload,
            "edges": [
                {
                    "uid": edge.uid,
                    "source_node_uid": edge.source_node_uid,
                    "source_port_name": edge.source_port_name,
                    "target_node_uid": edge.target_node_uid,
                    "target_port_name": edge.target_port_name,
                    "condition_label": edge.condition_label,
                    "graph_meta": dict(edge.graph_meta or {}),
                }
                for edge in self.edges.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowGraph":
        """从字典结构创建工作流。

        Args:
            data: 工作流字典。

        Returns:
            构造后的工作流对象。

        Raises:
            FlowGraphError: 当输入结构缺失关键字段时抛出。
        """

        workflow_uid = str(data.get("uid") or "").strip()
        if not workflow_uid:
            raise FlowGraphError("工作流字典缺少 uid。")

        workflow = cls(uid=workflow_uid)

        for node_data in data.get("nodes", []):
            node_uid = str(node_data.get("uid") or "").strip()
            if not node_uid:
                raise FlowGraphError("节点字段 uid 不能为空。")
            input_ports = {
                key: NodePort(**value)
                for key, value in (node_data.get("input_ports") or {}).items()
            }
            output_ports = {
                key: NodePort(**value)
                for key, value in (node_data.get("output_ports") or {}).items()
            }
            content = NodeContent.from_mapping(node_data.get("content") or {}, node_uid=node_uid)
            node = Node(
                uid=node_uid,
                node_type=node_data["node_type"],
                is_leaf=bool(node_data.get("is_leaf", False)),
                is_business_node=bool(node_data.get("is_business_node", True)),
                is_graph_node=bool(node_data.get("is_graph_node", False)),
                graph_meta=dict(node_data.get("graph_meta") or {}),
                allow_multi_input_ports=[
                    str(x).strip()
                    for x in (node_data.get("allow_multi_input_ports") or [])
                    if str(x).strip()
                ],
                input_ports=input_ports,
                output_ports=output_ports,
                content=content,
            )
            workflow.add_node(node)

        for edge_data in data.get("edges", []):
            edge = Edge(**edge_data)
            workflow.add_edge(edge)

        return workflow
