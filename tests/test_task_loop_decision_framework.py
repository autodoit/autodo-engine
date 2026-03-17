"""决策规则框架集成测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoengine import api
from autodoengine.taskdb import decision_store


class TestTaskLoopDecisionFramework(unittest.TestCase):
    """决策规则框架测试用例。"""

    def test_direct_node_ignore_node_level_control(self) -> None:
        """直流节点应忽略节点级控制项并按默认直行。"""

        graph_payload = {
            "graph_uid": "graph-decision-framework-direct",
            "graph_name": "决策框架-直流节点",
            "graph_version": "0.1.0",
            "policies": {
                "decision_department": {
                    "intervention_condition": "abnormal_upgrade",
                    "members": ["pa"],
                }
            },
            "nodes": [
                {
                    "node_uid": "node-start",
                    "node_type": "start",
                    "affair_uid": "affair-start",
                    "policies": {
                        "route_mode": "direct",
                        "decision_department": {
                            "intervention_condition": "always",
                            "members": ["human"],
                        }
                    },
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
                    "edge_uid": "edge-direct-1",
                    "from_node_uid": "node-start",
                    "to_node_uid": "node-end",
                    "enabled": True,
                }
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
                title="直流节点测试",
                goal_text="验证节点级控制失效",
                current_node_uid="node-start",
            )

            decision = api.run_task_step(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid)
            rows = decision_store.list_task_decisions(str(task["task_uid"]))

        self.assertEqual(decision.selected_action.value, "continue")
        self.assertEqual(decision.decision_actor, "decision_department")
        self.assertEqual(decision.decision_mode, "PA-only")
        self.assertGreaterEqual(len(rows), 1)
        packet = rows[-1].get("packet") or {}
        self.assertEqual(packet.get("decision_mode"), "PA-only")

    def test_decision_node_abnormal_upgrade_to_pa(self) -> None:
        """决策节点在异常升级模式应进入 PA 决策。"""

        graph_payload = {
            "graph_uid": "graph-decision-framework-pa",
            "graph_name": "决策框架-PA介入",
            "graph_version": "0.1.0",
            "policies": {
                "decision_department": {
                    "intervention_condition": "abnormal_upgrade",
                    "members": ["pa"],
                }
            },
            "nodes": [
                {
                    "node_uid": "node-pa",
                    "node_type": "process",
                    "affair_uid": "affair-pa",
                    "policies": {
                        "route_mode": "decision",
                        "simulate_receipt": {
                            "result_code": "BLOCKED",
                            "block_reason_code": "permission_missing",
                            "block_scope": "node",
                            "requires_human": True,
                            "retryable": False,
                            "message": "需要权限",
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
                title="PA介入测试",
                goal_text="验证异常升级到PA",
                current_node_uid="node-pa",
            )

            decision = api.run_task_step(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid)

        self.assertEqual(decision.decision_actor, "decision_department")
        self.assertEqual(decision.decision_members, ["pa"])
        self.assertEqual(decision.selected_action.value, "human_gate")

    def test_decision_node_human_actor_forced_gate(self) -> None:
        """决策节点配置人工主体时应进入 human_gate。"""

        graph_payload = {
            "graph_uid": "graph-decision-framework-human",
            "graph_name": "决策框架-人工介入",
            "graph_version": "0.1.0",
            "policies": {
                "decision_department": {
                    "intervention_condition": "abnormal_upgrade",
                    "members": ["pa"],
                }
            },
            "nodes": [
                {
                    "node_uid": "node-human",
                    "node_type": "process",
                    "affair_uid": "affair-human",
                    "policies": {
                        "route_mode": "decision",
                        "decision_department": {
                            "intervention_condition": "always",
                            "members": ["human"],
                        },
                        "simulate_receipt": {
                            "result_code": "BLOCKED",
                            "block_reason_code": "permission_missing",
                            "block_scope": "node",
                            "requires_human": True,
                            "retryable": False,
                            "message": "需要人工介入",
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
                title="人工介入测试",
                goal_text="验证人工介入",
                current_node_uid="node-human",
            )

            decision = api.run_task_step(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid)

        self.assertEqual(decision.decision_actor, "decision_department")
        self.assertEqual(decision.decision_members, ["human"])
        self.assertEqual(decision.selected_action.value, "human_gate")


if __name__ == "__main__":
    unittest.main()

