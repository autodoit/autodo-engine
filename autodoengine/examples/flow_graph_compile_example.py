"""流程图 -> workflow.json 的最小编译示例。

运行方式（仓库根目录）：

```powershell
python -m autodoengine.examples.flow_graph_compile_example
```
"""

from __future__ import annotations

from pathlib import Path

from autodoengine.utils.path_tools import find_repo_root
from autodoengine.flow_graph import (
    Edge,
    FlowGraph,
    NodeTemplate,
    create_node_from_template,
    load_node_templates,
    compile_flow_graph_to_workflow_dict,
    write_workflow_json,
)


def build_demo_graph() -> FlowGraph:
    """构建一个使用节点模板的示例流程图。

    Returns:
        FlowGraph 对象。
    """

    templates = load_node_templates()
    t_import: NodeTemplate = templates["导入和预处理文献元数据"]
    t_pdf_to_docs: NodeTemplate = templates["从PDF提取可检索文本"]
    t_chunk: NodeTemplate = templates["解析与分块"]
    t_index: NodeTemplate = templates["向量化与索引构建"]

    wf = FlowGraph(uid="workflow_flow_graph_demo")

    node_import = create_node_from_template(
        t_import,
        node_uid="导入和预处理文献元数据",
        payload={
            "output_dir": "workflows/workflow_flow_graph_demo/data/题录导出文件",
        },
    )
    node_pdf_to_docs = create_node_from_template(
        t_pdf_to_docs,
        node_uid="从PDF提取可检索文本",
        payload={
            "input_table_csv": "workflows/workflow_flow_graph_demo/data/题录导出文件/文献数据表.csv",
            "output_dir": "workflows/workflow_flow_graph_demo/output/02_pdf_to_docs",
        },
    )
    node_chunk = create_node_from_template(
        t_chunk,
        node_uid="解析与分块",
        payload={
            "input_docs_jsonl": "workflows/workflow_flow_graph_demo/output/02_pdf_to_docs/docs.jsonl",
            "output_dir": "workflows/workflow_flow_graph_demo/output/03_chunk",
        },
    )
    node_index = create_node_from_template(
        t_index,
        node_uid="向量化与索引构建",
        payload={
            "input_chunks_jsonl": "workflows/workflow_flow_graph_demo/output/03_chunk/chunks.jsonl",
            "output_dir": "workflows/workflow_flow_graph_demo/output/04_vector_index",
        },
    )

    wf.add_node(node_import)
    wf.add_node(node_pdf_to_docs)
    wf.add_node(node_chunk)
    wf.add_node(node_index)

    wf.add_edge(
        Edge(
            uid="edge-1",
            source_node_uid=node_import.uid,
            source_port_name="table",
            target_node_uid=node_pdf_to_docs.uid,
            target_port_name="table",
        )
    )
    wf.add_edge(
        Edge(
            uid="edge-2",
            source_node_uid=node_pdf_to_docs.uid,
            source_port_name="docs",
            target_node_uid=node_chunk.uid,
            target_port_name="docs",
        )
    )
    wf.add_edge(
        Edge(
            uid="edge-3",
            source_node_uid=node_chunk.uid,
            source_port_name="chunks",
            target_node_uid=node_index.uid,
            target_port_name="chunks",
        )
    )
    return wf


def main() -> None:
    """编译并写出 workflow.json。"""

    repo_root = find_repo_root(Path(__file__))
    out_dir = (repo_root / "demos" / "workflows" / "workflow_flow_graph_demo").resolve()
    out_path = (out_dir / "workflow.json").resolve()

    graph = build_demo_graph()
    templates = load_node_templates()
    templates_by_content_ref = {t.content_ref: t for t in templates.values()}

    workflow_dict = compile_flow_graph_to_workflow_dict(
        graph,
        templates_by_content_ref=templates_by_content_ref,
        workflow_id="workflow_flow_graph_demo",
        workflow_name="FlowGraph 编译示例（可直接运行）",
        emit_flow_groups=True,
    )

    write_workflow_json(workflow_dict, out_path)
    print(f"已写出：{out_path}")


if __name__ == "__main__":
    main()

