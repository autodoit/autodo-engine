"""task_loop BLOCKED + human_gate 集成测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoengine import api
from autodoengine.taskdb import log_store, task_store


class TestTaskLoopBlocked(unittest.TestCase):
    """BLOCKED 场景测试。"""

    def test_blocked_human_gate(self) -> None:
        """应进入 blocked 并标记 human_gate_pending。"""

        graph_payload = {
            "graph_uid": "graph-blocked",
            "graph_name": "阻断图",
            "graph_version": "0.1.0",
            "nodes": [
                {
                    "node_uid": "node-blocked",
                    "node_type": "process",
                    "affair_uid": "affair-blocked",
                    "policies": {
                        "simulate_receipt": {
                            "result_code": "BLOCKED",
                            "block_reason_code": "permission_missing",
                            "block_scope": "node",
                            "requires_human": True,
                            "retryable": False,
                            "message": "权限不足"
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

            task = api.create_task(
                title="阻断任务",
                goal_text="测试 human gate",
                current_node_uid="node-blocked",
            )

            decisions = api.run_task_until_wait(
                task_uid=str(task["task_uid"]),
                graph_uid=graph.graph_uid,
                max_steps=3,
            )

            latest_task = task_store.get_task(str(task["task_uid"]))

        self.assertGreaterEqual(len(decisions), 1)
        self.assertEqual(latest_task["status"], "blocked")
        self.assertTrue(bool((latest_task.get("metadata") or {}).get("human_gate_pending", False)))

    def test_aa_fallback_triggered_and_logged(self) -> None:
        """脚本阻断且无需人工时应触发 LLM 兜底并写入审计事件。"""

        graph_payload = {
            "graph_uid": "graph-aa-fallback",
            "graph_name": "AA兜底图",
            "graph_version": "0.1.0",
            "nodes": [
                {
                    "node_uid": "node-fallback",
                    "node_type": "process",
                    "affair_uid": "affair-fallback",
                    "policies": {
                        "simulate_receipt": {
                            "result_code": "BLOCKED",
                            "block_reason_code": "dependency_unready",
                            "block_scope": "affair",
                            "requires_human": False,
                            "retryable": False,
                            "message": "脚本执行失败"
                        },
                        "simulate_llm_fallback_receipt": {
                            "result_code": "PASS",
                            "output_payload": {"artifacts": []},
                            "message": "兜底成功"
                        },
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

            task = api.create_task(
                title="AA兜底任务",
                goal_text="测试AA兜底日志",
                current_node_uid="node-fallback",
            )

            api.run_task_step(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid)
            events = log_store.list_runtime_events(str(task["task_uid"]))

        event_types = [str((item.get("event_type") or "")) for item in events]
        self.assertIn("aa_fallback_triggered", event_types)
        self.assertTrue(any(kind in {"aa_fallback_completed", "aa_fallback_failed"} for kind in event_types))

        normalized_events = [item for item in events if str(item.get("event_type")) == "receipt_normalized"]
        self.assertGreaterEqual(len(normalized_events), 1)
        payload = dict((normalized_events[-1].get("payload") or {}))
        self.assertEqual(str(payload.get("aa_handling_mode")), "llm_fallback")
        self.assertEqual(int(payload.get("fallback_attempt") or 0), 1)


if __name__ == "__main__":
    unittest.main()

