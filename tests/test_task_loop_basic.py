"""task_loop 基础闭环测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoengine import api
from autodoengine.taskdb import decision_store, log_store, task_store


class TestTaskLoopBasic(unittest.TestCase):
    """task_loop 基础闭环测试用例。"""

    def test_run_task_until_terminal_completed(self) -> None:
        """测试最小图可推进到 completed。"""

        graph_payload = {
            "graph_uid": "graph-test-loop",
            "graph_name": "闭环测试图",
            "graph_version": "0.1.0",
            "nodes": [
                {
                    "node_uid": "node-start",
                    "node_type": "start",
                    "affair_uid": "affair-start",
                    "enabled": True,
                },
                {
                    "node_uid": "node-mid",
                    "node_type": "process",
                    "affair_uid": "affair-mid",
                    "enabled": True,
                },
                {
                    "node_uid": "node-end",
                    "node_type": "end",
                    "affair_uid": "affair-end",
                    "policies": {"goal_satisfied_at_node": True},
                    "enabled": True,
                },
            ],
            "edges": [
                {
                    "edge_uid": "edge-1",
                    "from_node_uid": "node-start",
                    "to_node_uid": "node-mid",
                    "enabled": True,
                },
                {
                    "edge_uid": "edge-2",
                    "from_node_uid": "node-mid",
                    "to_node_uid": "node-end",
                    "enabled": True,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            graph_file = Path(temp_dir) / "graph.json"
            graph_file.write_text(json.dumps(graph_payload, ensure_ascii=False), encoding="utf-8")

            api.bootstrap_runtime(str(runtime_root))
            graph = api.load_graph(str(graph_file))
            api.register_graph(graph)

            task = api.create_task(
                title="测试任务",
                goal_text="验证闭环",
                current_node_uid="node-start",
            )

            decisions = api.run_task_until_terminal(
                task_uid=str(task["task_uid"]),
                graph_uid=graph.graph_uid,
                max_steps=5,
            )

            latest_task = task_store.get_task(str(task["task_uid"]))
            decision_rows = decision_store.list_task_decisions(str(task["task_uid"]))
            event_rows = log_store.list_runtime_events(str(task["task_uid"]))

        self.assertGreaterEqual(len(decisions), 1)
        self.assertEqual(latest_task["status"], "completed")
        self.assertEqual(len(decision_rows), len(decisions))
        self.assertGreaterEqual(len(event_rows), len(decisions))


if __name__ == "__main__":
    unittest.main()

