"""事务请求与决策部门存储测试。"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import json

from autodoengine import api
from autodoengine.taskdb import department_store, request_store
from autodoengine.taskdb.storage_paths import get_runtime_store_files


class TestTaskdbRequestAndDepartmentStore(unittest.TestCase):
    """验证新任务网络存储对象。"""

    def test_run_task_request_can_consume_pending_request(self) -> None:
        """应能正式消费待调度事务请求并回写结果。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            workspace_root = project_root / "workspace"
            config_dir = workspace_root / "config" / "affairs_config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "A010.json"
            config_path.write_text("{}", encoding="utf-8")

            api.bootstrap_runtime(str(workspace_root))
            task = api.create_task(title="测试任务", goal_text="验证请求执行", current_node_uid="A010")
            request = api.create_task_request(
                request_type="事务执行",
                target_affair_uid="ar_A010_项目初始化",
                task_uid=str(task["task_uid"]),
                source_object_type="节点",
                source_object_uid="A010",
                node_code="A010",
                config_path=str(config_path),
                payload={"workspace_root": str(workspace_root)},
            )

            original_run_affair = api.run_affair

            def _fake_run_affair(affair_uid: str, *, config_path: str | Path | None = None, workspace_root: str | Path | None = None, config: dict | None = None):
                self.assertEqual(affair_uid, "ar_A010_项目初始化")
                self.assertTrue(Path(str(config_path)).exists())
                self.assertEqual(Path(str(workspace_root)).resolve(), workspace_root_path.resolve())
                return [workspace_root_path / "workspace" / "artifacts" / "done.txt"]

            workspace_root_path = workspace_root
            api.run_affair = _fake_run_affair
            try:
                result = api.run_task_request(str(request["request_uid"]))
            finally:
                api.run_affair = original_run_affair

            refreshed_request = api.get_task_request(str(request["request_uid"]))
            refreshed_task = api.task_store.get_task(str(task["task_uid"]))

        self.assertEqual(result["status"], "completed")
        self.assertEqual(refreshed_request["status"], "已完成")
        self.assertEqual(refreshed_task["status"], "running")
        self.assertEqual(result["node_code"], "A010")

    def test_project_mainflow_runner_can_build_and_consume_project_requests(self) -> None:
        """应能从项目 config 构造主链请求并完成最小主链模拟运行。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            workspace_root = project_root / "workspace"
            config_root = workspace_root / "config"
            affairs_config_root = config_root / "affairs_config"
            affairs_config_root.mkdir(parents=True, exist_ok=True)
            (workspace_root / "database" / "tasks").mkdir(parents=True, exist_ok=True)
            (workspace_root / "database" / "logs").mkdir(parents=True, exist_ok=True)
            (workspace_root / "database" / "decision").mkdir(parents=True, exist_ok=True)

            graph_path = project_root / ".autodoengine" / "workflows" / "demo" / "graph.json"
            graph_path.parent.mkdir(parents=True, exist_ok=True)
            graph_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"node_uid": "n_A010", "enabled": True},
                            {"node_uid": "n_A020", "enabled": True},
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            a010_config = affairs_config_root / "A010.json"
            a020_config = affairs_config_root / "A020.json"
            a010_config.write_text("{}", encoding="utf-8")
            a020_config.write_text("{}", encoding="utf-8")

            registry_path = config_root / "affair_entry_registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "node_code": "A010",
                                "affair_uid": "ar_A010_项目初始化",
                                "config_path": str(a010_config),
                                "implemented": True,
                            },
                            {
                                "node_code": "A020",
                                "affair_uid": "ar_A020_文献导入与预处理",
                                "config_path": str(a020_config),
                                "implemented": True,
                            },
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            project_config_path = config_root / "config.json"
            project_config_path.write_text(
                json.dumps(
                    {
                        "workflow_name": "测试项目",
                        "workspace_root": str(workspace_root),
                        "project": {"project_name": "测试项目", "project_goal": "验证主链 runner"},
                        "runtime": {
                            "workflow_graph_path": str(graph_path),
                            "start_node": "A010",
                            "end_node": "A020",
                            "user_action_routing": {
                                "execute": "aoe.run",
                                "continue": "aoe.resume",
                                "pause": "aoe.pause",
                                "retry": "aoe.retry_current",
                                "fallback": "aoe.fallback_current",
                                "stop": "aoe.stop",
                                "gate_pass": "aoe.gate_pass",
                            },
                        },
                        "paths": {"affair_entry_registry_path": str(registry_path)},
                        "node_inputs": {"A010": str(a010_config), "A020": str(a020_config)},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = api.run_project_mainflow(project_config_path=str(project_config_path), simulate=True)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["validate"]["ok"], True)
        self.assertEqual([item["node_code"] for item in result["events"]], ["A010", "A020"])
        self.assertTrue(all(item["status"] == "simulated" for item in result["events"]))
        self.assertTrue(all(item["status"] == "已完成" for item in result["requests"]))

    def test_request_and_department_tables_use_chinese_contract(self) -> None:
        """应创建中文表并写入中文状态与默认百炼配置。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            api.bootstrap_runtime(str(runtime_root))

            department = department_store.ensure_default_department()
            request = request_store.create_request(
                request_type="事务执行",
                target_affair_uid="affair-demo",
                task_uid="task-demo",
                source_object_type="节点",
                source_object_uid="A010",
                node_code="A010",
                config_path="workspace/config/affairs_config/A010.json",
                request_contract={"entry_config": "workspace/config/affairs_config/A010.json"},
                payload={"workspace_root": "."},
                priority_score=3.5,
            )

            files = get_runtime_store_files()
            with closing(sqlite3.connect(str(files["tasks_db"]))) as task_connection:
                task_tables = {
                    str(row[0])
                    for row in task_connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                request_status = task_connection.execute(
                    'SELECT "请求状态", "来源对象类型", "来源对象UID", "节点编码", "配置路径" FROM "事务请求" WHERE uid_请求=?',
                    (request["uid_请求"],),
                ).fetchone()

            with closing(sqlite3.connect(str(files["decision_db"]))) as decision_connection:
                decision_tables = {
                    str(row[0])
                    for row in decision_connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                vendor_row = decision_connection.execute(
                    'SELECT "默认LLM供应商" FROM "决策部门" WHERE uid_部门=?',
                    (department["uid_部门"],),
                ).fetchone()
                member_rows = decision_connection.execute(
                    'SELECT "成员类型" FROM "决策成员" WHERE uid_部门=? ORDER BY "创建时间"',
                    (department["uid_部门"],),
                ).fetchall()

        self.assertIn("事务请求", task_tables)
        self.assertIn("决策部门", decision_tables)
        self.assertIn("决策成员", decision_tables)
        self.assertIsNotNone(request_status)
        self.assertEqual(str(request_status[0]), "待调度")
        self.assertEqual(str(request_status[1]), "节点")
        self.assertEqual(str(request_status[2]), "A010")
        self.assertEqual(str(request_status[3]), "A010")
        self.assertEqual(str(request_status[4]), "workspace/config/affairs_config/A010.json")
        self.assertIsNotNone(vendor_row)
        self.assertEqual(str(vendor_row[0]), "阿里百炼")
        self.assertEqual({str(row[0]) for row in member_rows}, {"LLM", "人类"})

    def test_request_builder_can_ingest_project_node_contract(self) -> None:
        """应能从项目 config 与节点编码生成桥接请求。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            project_root = Path(temp_dir) / "project"
            workspace_root = project_root / "workspace"
            config_dir = workspace_root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)

            registry_path = config_dir / "affair_entry_registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "node_code": "A010",
                                "affair_uid": "ar_A010_项目初始化",
                                "config_path": str(config_dir / "affairs_config" / "A010.json"),
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            affair_config_path = config_dir / "affairs_config" / "A010.json"
            affair_config_path.parent.mkdir(parents=True, exist_ok=True)
            affair_config_path.write_text("{}", encoding="utf-8")

            project_config_path = config_dir / "config.json"
            project_config_path.write_text(
                json.dumps(
                    {
                        "workspace_root": str(workspace_root),
                        "paths": {"affair_entry_registry_path": str(registry_path)},
                        "node_inputs": {"A010": str(affair_config_path)},
                        "node_contracts": {"A010": {"entry_config": str(affair_config_path), "primary_transport": "文献流程状态"}},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            api.bootstrap_runtime(str(runtime_root))
            request = api.create_task_request_from_project_node(
                project_config_path=str(project_config_path),
                node_code="A010",
                task_uid="task-ark-demo",
            )

        self.assertEqual(request["target_affair_uid"], "ar_A010_项目初始化")
        self.assertEqual(request["source_object_type"], "节点")
        self.assertEqual(request["source_object_uid"], "A010")
        self.assertEqual(request["node_code"], "A010")
        self.assertIn("workspace", request["config_path"])
        self.assertEqual(request["request_contract"]["primary_transport"], "文献流程状态")


if __name__ == "__main__":
    unittest.main()