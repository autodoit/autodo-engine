"""流程图装载摘要工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from autodoengine.flow_graph import load_graph_from_file


def load_graph_summary(graph_file: str | Path) -> Dict[str, Any]:
    """加载流程图并返回摘要。

    Args:
        graph_file: 流程图 JSON 文件路径。

    Returns:
        图摘要字典。
    """

    graph_path = Path(graph_file).resolve()
    graph = load_graph_from_file(str(graph_path))
    return {
        "graph_uid": graph.graph_uid,
        "graph_file": str(graph_path),
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
    }
