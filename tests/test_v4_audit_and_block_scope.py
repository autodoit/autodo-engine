"""v4 审计视图与阻断上浮测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoengine import api


class TestV4AuditAndBlockScope(unittest.TestCase):
    """v4 审计能力测试。"""

    def test_block_scope_lifted_and_audit_views(self) -> None:
        """BLOCKED 且 requires_human 时应上浮到 task，并可被审计视图聚合。"""

        graph_payload = {
            "graph_uid": "graph-v4-audit-1",
            "graph_name": "v4 审计图",
            "graph_version": "0.1.0",
            "policies": {
                "decision_department": {
                    "intervention_condition": "abnormal_upgrade",
                    "members": ["pa", "human"],
                    "decision_mode": "JOINT",
                }
            },
            "nodes": [
                {
                    "node_uid": "node-a",
                    "node_type": "process",
                    "affair_uid": "affair-a",
                    "risk_level": "normal",
                    "policies": {
                        "route_mode": "decision",
                        "simulate_receipt": {
                            "result_code": "BLOCKED",
                            "block_reason_code": "dependency_unready",
                            "block_scope": "affair",
                            "requires_human": True,
                            "retryable": False,
                            "message": "依赖未就绪并需人工",
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
                title="v4审计测试",
                goal_text="验证阻断上浮",
                current_node_uid="node-a",
            )

            api.run_task_step(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid)

            full_chain = api.get_task_full_chain_view(str(task["task_uid"]))
            department_view = api.get_decision_department_view(task_uid=str(task["task_uid"]))
            blocked_view = api.get_blocked_governance_view(task_uid=str(task["task_uid"]))

        events = full_chain.get("events") or []
        self.assertTrue(any(str(item.get("event_type")) == "block_scope_lifted" for item in events))
        self.assertTrue(any(str(item.get("event_type")) == "decision_finalized" for item in events))

        self.assertGreaterEqual(int(full_chain.get("step_count") or 0), 1)
        self.assertGreaterEqual(int(department_view.get("decision_count") or 0), 1)

        by_reason = blocked_view.get("by_block_reason_code") or {}
        self.assertIn("dependency_unready", by_reason)
        self.assertGreaterEqual(int((by_reason["dependency_unready"] or {}).get("task_level") or 0), 1)


if __name__ == "__main__":
    unittest.main()

