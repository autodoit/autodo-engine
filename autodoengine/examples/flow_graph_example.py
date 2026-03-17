"""流程图最小示例。"""

from __future__ import annotations

from autodoengine.flow_graph import Edge, Node, NodeContent, NodePort, FlowGraph


def build_minimal_workflow() -> FlowGraph:
    """构建一个最简流程图示例。

    Returns:
        包含两个节点和一条有向连线的流程图对象。

    Examples:
        >>> wf = build_minimal_workflow()
        >>> len(wf.nodes), len(wf.edges)
        (2, 1)
    """

    workflow = FlowGraph(uid="workflow-demo-001")

    source_node = Node(
        uid="node-source",
        node_type="source",
        is_leaf=False,
        input_ports={},
        output_ports={"result": NodePort(name="result", data_type="text")},
        content=NodeContent(
            affair_key="文献矩阵",
            payload={"input": "data/original", "output": "data/output"},
        ),
    )

    target_node = Node(
        uid="node-target",
        node_type="sink",
        is_leaf=True,
        input_ports={"in": NodePort(name="in", data_type="text")},
        output_ports={},
        content=NodeContent(
            affair_key="综述草稿生成",
            payload={"template": "default"},
        ),
    )

    workflow.add_node(source_node)
    workflow.add_node(target_node)

    workflow.add_edge(
        Edge(
            uid="edge-1",
            source_node_uid="node-source",
            source_port_name="result",
            target_node_uid="node-target",
            target_port_name="in",
        )
    )

    return workflow


def main() -> None:
    """运行示例并打印工作流字典。"""

    workflow = build_minimal_workflow()
    print(workflow.to_dict())


if __name__ == "__main__":
    main()

