"""task_loop split/resume 集成测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoengine import api
from autodoengine.taskdb import relation_store, task_store


class TestTaskLoopSplitResume(unittest.TestCase):
    """split -> suspended -> child completed -> parent ready 测试。"""

    def test_split_then_resume_to_ready(self) -> None:
        """父任务应可在子任务完成后恢复为 ready。"""

        graph_payload = {
            "graph_uid": "graph-split",
            "graph_name": "拆分图",
            "graph_version": "0.1.0",
            "nodes": [
                {
                    "node_uid": "node-split",
                    "node_type": "process",
                    "affair_uid": "affair-split",
                    "policies": {
                        "force_split_hint": True,
                        "simulate_receipt": {
                            "result_code": "BLOCKED",
                            "block_reason_code": "goal_ambiguous",
                            "block_scope": "task",
                            "requires_human": False,
                            "retryable": False,
                            "message": "目标不明确，需要拆分"
                        }
                    },
                    "enabled": True,
                }
            ],
            "edges": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            graph_file = Path(temp_dir) / "graph.json"
            graph_file.write_text(json.dumps(graph_payload, ensure_ascii=False), encoding="utf-8")

            api.bootstrap_runtime(str(runtime_root))
            graph = api.load_graph(str(graph_file))
            api.register_graph(graph)

            parent = api.create_task(
                title="父任务",
                goal_text="测试 split/resume",
                current_node_uid="node-split",
            )
            parent_uid = str(parent["task_uid"])

            first = api.run_task_step(task_uid=parent_uid, graph_uid=graph.graph_uid)
            self.assertEqual(first.task_status_after.value, "suspended")

            child_relations = relation_store.list_children(parent_uid)
            self.assertGreaterEqual(len(child_relations), 1)

            for relation in child_relations:
                task_store.mark_task_completed(str(relation["child_task_uid"]))

            resumed = api.run_task_step(task_uid=parent_uid, graph_uid=graph.graph_uid)
            self.assertEqual(resumed.task_status_after.value, "ready")

            latest_parent = task_store.get_task(parent_uid)
            self.assertEqual(latest_parent["status"], "ready")


if __name__ == "__main__":
    unittest.main()

