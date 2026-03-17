"""图加载与校验测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoengine.core.errors import GraphValidationError
from autodoengine.flow_graph import load_graph_from_dict, load_graph_from_file


class TestGraphLoader(unittest.TestCase):
    """图加载测试用例。

    Args:
        无。

    Returns:
        None。

    Raises:
        AssertionError: 当断言失败时抛出。

    Examples:
        >>> case = TestGraphLoader()
        >>> isinstance(case, unittest.TestCase)
        True
    """

    def test_load_graph_from_dict_success(self) -> None:
        """测试从字典加载图成功。"""

        graph = load_graph_from_dict(
            {
                "graph_uid": "graph-test",
                "graph_name": "测试图",
                "graph_version": "0.1.0",
                "nodes": [
                    {
                        "node_uid": "node-a",
                        "node_type": "start",
                        "affair_uid": "affair-a",
                        "enabled": True,
                    },
                    {
                        "node_uid": "node-b",
                        "node_type": "end",
                        "affair_uid": "affair-b",
                        "enabled": True,
                    },
                ],
                "edges": [
                    {
                        "edge_uid": "edge-a-b",
                        "from_node_uid": "node-a",
                        "to_node_uid": "node-b",
                        "enabled": True,
                    }
                ],
            }
        )

        self.assertEqual(graph.graph_uid, "graph-test")
        self.assertIn("node-a", graph.nodes)
        self.assertEqual(len(graph.edges), 1)

    def test_load_graph_from_file_success(self) -> None:
        """测试从文件加载图成功。"""

        payload = {
            "graph_uid": "graph-file",
            "graph_name": "文件图",
            "graph_version": "0.1.0",
            "nodes": [
                {
                    "node_uid": "node-start",
                    "node_type": "start",
                    "affair_uid": "affair-start",
                    "enabled": True,
                },
                {
                    "node_uid": "node-end",
                    "node_type": "end",
                    "affair_uid": "affair-end",
                    "enabled": True,
                },
            ],
            "edges": [
                {
                    "edge_uid": "edge-start-end",
                    "from_node_uid": "node-start",
                    "to_node_uid": "node-end",
                    "enabled": True,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "graph.json"
            file_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            graph = load_graph_from_file(str(file_path))

        self.assertEqual(graph.graph_uid, "graph-file")
        self.assertEqual(graph.graph_name, "文件图")

    def test_invalid_edge_should_raise(self) -> None:
        """测试边引用不存在节点时抛异常。"""

        with self.assertRaises(GraphValidationError):
            load_graph_from_dict(
                {
                    "graph_uid": "graph-invalid",
                    "graph_name": "非法图",
                    "graph_version": "0.1.0",
                    "nodes": [
                        {
                            "node_uid": "node-only",
                            "node_type": "start",
                            "affair_uid": "affair-only",
                            "enabled": True,
                        }
                    ],
                    "edges": [
                        {
                            "edge_uid": "edge-bad",
                            "from_node_uid": "node-only",
                            "to_node_uid": "node-missing",
                            "enabled": True,
                        }
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()

