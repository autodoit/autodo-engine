"""流程图 -> workflow.json 的最小编译示例（通用、自包含、可确定运行）。

运行方式（仓库根目录）：

```bash
python -m autodoengine.examples.flow_graph_compile_example
```

演示 AOF/前端编译链的核心能力：用合成的节点模板搭一张三节点线性图，
编译为 `node_runtime_v2` 结构的 workflow 字典并落盘。示例使用学科无关的
占位事务（demo_extract / demo_transform / demo_load），不引入任何领域术语，
也不依赖外部事务库。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from autodoengine.flow_graph import (
    Edge,
    FlowGraph,
    NodePort,
    NodeTemplate,
    compile_flow_graph_to_workflow_dict,
    create_node_from_template,
    write_workflow_json,
)


def _demo_template(key: str, *, out_port: str | None, in_port: str | None) -> NodeTemplate:
    """构造一个学科无关的合成事务模板。

    Args:
        key: 事务标识（同时作为 content_ref）。
        out_port: 输出端口名；None 表示叶子。
        in_port: 输入端口名；None 表示无上游。

    Returns:
        可直接用于 `create_node_from_template` 的 `NodeTemplate`。
    """

    return NodeTemplate(
        id=key,
        uid=f"node-tpl-{key}",
        content_kind="affair",
        content_ref=key,
        content_payload={},
        node_type="process",
        is_leaf=out_port is None,
        is_business_node=True,
        is_graph_node=False,
        allow_multi_input_ports=[],
        input_ports={} if in_port is None else {in_port: NodePort(name=in_port, data_type="any")},
        output_ports={} if out_port is None else {out_port: NodePort(name=out_port, data_type="any")},
        affair={"type": key, "config": {}},
    )


def build_demo_graph() -> FlowGraph:
    """构建 extract -> transform -> load 三节点线性流程图。

    Returns:
        FlowGraph 对象。
    """

    templates = [
        _demo_template("demo_extract", out_port="rows", in_port=None),
        _demo_template("demo_transform", out_port="rows", in_port="rows"),
        _demo_template("demo_load", out_port=None, in_port="rows"),
    ]

    wf = FlowGraph(uid="workflow_flow_graph_demo")
    for tmpl in templates:
        wf.add_node(create_node_from_template(tmpl, node_uid=tmpl.content_ref))

    wf.add_edge(
        Edge(
            uid="edge-1",
            source_node_uid="demo_extract",
            source_port_name="rows",
            target_node_uid="demo_transform",
            target_port_name="rows",
        )
    )
    wf.add_edge(
        Edge(
            uid="edge-2",
            source_node_uid="demo_transform",
            source_port_name="rows",
            target_node_uid="demo_load",
            target_port_name="rows",
        )
    )
    return wf


def compile_demo() -> dict:
    """编译示例图为 workflow 字典。

    Returns:
        可直接写入 JSON 的 workflow 字典。
    """

    templates_by_content_ref = {
        tmpl.content_ref: tmpl
        for tmpl in [
            _demo_template("demo_extract", out_port="rows", in_port=None),
            _demo_template("demo_transform", out_port="rows", in_port="rows"),
            _demo_template("demo_load", out_port=None, in_port="rows"),
        ]
    }
    return compile_flow_graph_to_workflow_dict(
        build_demo_graph(),
        templates_by_content_ref=templates_by_content_ref,
        workflow_id="workflow_flow_graph_demo",
        workflow_name="FlowGraph 编译示例",
        emit_flow_groups=True,
    )


def main() -> None:
    """编译并写出 workflow.json 到临时目录，打印结构摘要。"""

    workflow_dict = compile_demo()
    with tempfile.TemporaryDirectory() as temp_dir:
        out_path = write_workflow_json(workflow_dict, Path(temp_dir) / "workflow.json")
        print(f"已写出：{out_path}")
    print("workflow_id:", workflow_dict["workflow_id"])
    print("schema_version:", workflow_dict["schema_version"])
    print("flow:", workflow_dict["flow"])
    print("flow_groups:", workflow_dict["flow_groups"])
    print("affairs:", list(workflow_dict["affairs"].keys()))


if __name__ == "__main__":
    main()
