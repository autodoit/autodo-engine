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

    def test_request_lease_should_be_exclusive_and_recover_after_release(self) -> None:
        """同一请求租约应保持独占，释放后可再次领取。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            api.bootstrap_runtime(str(runtime_root))

            request = api.create_task_request(
                request_type="事务执行",
                target_affair_uid="ar_A010_项目初始化",
                node_code="A010",
                config_path=str(runtime_root / "workspace" / "config" / "affairs_config" / "A010.json"),
            )

            first = api.acquire_task_request_lease(
                executor_uid="agent-1",
                request_uid=str(request["request_uid"]),
                lease_seconds=120,
            )
            second = api.acquire_task_request_lease(
                executor_uid="agent-2",
                request_uid=str(request["request_uid"]),
                lease_seconds=120,
            )

            released = api.release_task_request_lease(
                request_uid=str(request["request_uid"]),
                executor_uid="agent-1",
                lease_status="已释放",
                heartbeat_status="空闲",
            )
            third = api.acquire_task_request_lease(
                executor_uid="agent-2",
                request_uid=str(request["request_uid"]),
                lease_seconds=120,
                statuses=["待调度", "待租约", "已租约"],
            )

            refreshed = api.get_task_request(str(request["request_uid"]))

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(released, True)
        self.assertIsNotNone(third)
        self.assertEqual(refreshed["executor_uid"], "agent-2")
        self.assertEqual(refreshed["status"], "已租约")

    def test_request_lease_should_allow_expired_takeover(self) -> None:
        """租约过期后应允许其他执行者接管。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            api.bootstrap_runtime(str(runtime_root))

            request = api.create_task_request(
                request_type="事务执行",
                target_affair_uid="ar_A020_文献导入与预处理",
                node_code="A020",
                config_path=str(runtime_root / "workspace" / "config" / "affairs_config" / "A020.json"),
            )

            first = api.acquire_task_request_lease(
                executor_uid="agent-1",
                request_uid=str(request["request_uid"]),
                lease_seconds=120,
            )
            self.assertIsNotNone(first)

            files = get_runtime_store_files()
            with closing(sqlite3.connect(str(files["tasks_db"]))) as connection, connection:
                connection.execute(
                    'UPDATE "资源租约" SET "过期时间"=?, "更新时间"=? WHERE uid_请求=?',
                    ("2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00", str(request["request_uid"])),
                )
                connection.execute(
                    'UPDATE "事务请求" SET "租约过期时间"=?, "更新时间"=? WHERE uid_请求=?',
                    ("2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00", str(request["request_uid"])),
                )

            second = api.acquire_task_request_lease(
                executor_uid="agent-2",
                request_uid=str(request["request_uid"]),
                lease_seconds=120,
                statuses=["待调度", "待租约", "已租约"],
            )
            refreshed = api.get_task_request(str(request["request_uid"]))

        self.assertIsNotNone(second)
        self.assertEqual(refreshed["executor_uid"], "agent-2")
        self.assertEqual(refreshed["status"], "已租约")

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
        self.assertEqual(str(result.get("result_code") or ""), "PASS")
        self.assertIn("output_payload", result)
        self.assertIn("executor_meta", result)

    def test_run_task_request_should_accept_standard_receipt_json(self) -> None:
        """标准回执 JSON 应透传为统一请求执行结果。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            workspace_root = project_root / "workspace"
            config_dir = workspace_root / "config" / "affairs_config"
            output_dir = workspace_root / "artifacts"
            config_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            config_path = config_dir / "A010.json"
            config_path.write_text("{}", encoding="utf-8")

            receipt_path = output_dir / "receipt.json"
            receipt_payload = {
                "result_code": "PASS",
                "message": "标准回执测试",
                "output_payload": {
                    "artifacts": [str(output_dir / "done.txt")],
                    "records": 1,
                },
                "executor_meta": {
                    "source": "unit-test",
                },
            }
            receipt_path.write_text(json.dumps(receipt_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            api.bootstrap_runtime(str(workspace_root))
            request = api.create_task_request(
                request_type="事务执行",
                target_affair_uid="ar_A010_项目初始化",
                node_code="A010",
                config_path=str(config_path),
                payload={"workspace_root": str(workspace_root)},
            )

            original_run_affair = api.run_affair

            def _fake_run_affair(
                affair_uid: str,
                *,
                config_path: str | Path | None = None,
                workspace_root: str | Path | None = None,
                config: dict | None = None,
            ):
                self.assertEqual(affair_uid, "ar_A010_项目初始化")
                return [receipt_path]

            api.run_affair = _fake_run_affair
            try:
                result = api.run_task_request(str(request["request_uid"]))
            finally:
                api.run_affair = original_run_affair

        self.assertEqual(str(result.get("status") or ""), "completed")
        self.assertEqual(str(result.get("result_code") or ""), "PASS")
        self.assertEqual(str(result.get("message") or ""), "标准回执测试")
        self.assertEqual(int((result.get("output_payload") or {}).get("records") or 0), 1)
        self.assertEqual(str((result.get("executor_meta") or {}).get("source") or ""), "unit-test")

    def test_run_task_request_should_map_blocked_receipt(self) -> None:
        """BLOCKED 回执应映射为请求阻断与任务阻断。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            workspace_root = project_root / "workspace"
            config_dir = workspace_root / "config" / "affairs_config"
            output_dir = workspace_root / "artifacts"
            config_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            config_path = config_dir / "A010.json"
            config_path.write_text("{}", encoding="utf-8")

            receipt_path = output_dir / "blocked_receipt.json"
            receipt_payload = {
                "result_code": "BLOCKED",
                "message": "等待人工确认",
                "output_payload": {
                    "artifacts": [],
                    "reason": "manual_gate",
                },
                "executor_meta": {
                    "requires_human": True,
                },
            }
            receipt_path.write_text(json.dumps(receipt_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            api.bootstrap_runtime(str(workspace_root))
            task = api.create_task(title="阻断测试", goal_text="验证 blocked 回执", current_node_uid="A010")
            request = api.create_task_request(
                request_type="事务执行",
                target_affair_uid="ar_A010_项目初始化",
                node_code="A010",
                task_uid=str(task["task_uid"]),
                config_path=str(config_path),
                payload={"workspace_root": str(workspace_root)},
            )

            original_run_affair = api.run_affair

            def _fake_run_affair(
                affair_uid: str,
                *,
                config_path: str | Path | None = None,
                workspace_root: str | Path | None = None,
                config: dict | None = None,
            ):
                self.assertEqual(affair_uid, "ar_A010_项目初始化")
                return [receipt_path]

            api.run_affair = _fake_run_affair
            try:
                result = api.run_task_request(str(request["request_uid"]))
            finally:
                api.run_affair = original_run_affair

            refreshed_request = api.get_task_request(str(request["request_uid"]))
            refreshed_task = api.task_store.get_task(str(task["task_uid"]))

        self.assertEqual(str(result.get("status") or ""), "blocked")
        self.assertEqual(str(result.get("result_code") or ""), "BLOCKED")
        self.assertEqual(str(refreshed_request.get("status") or ""), "已阻断")
        self.assertEqual(str(refreshed_task.get("status") or ""), "blocked")

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

    def test_project_mainflow_should_continue_after_ea_auto_audit(self) -> None:
        """EA 自动审计放行后，主链应继续运行。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            workspace_root = project_root / "workspace"
            config_root = workspace_root / "config"
            affairs_config_root = config_root / "affairs_config"
            output_root = workspace_root / "artifacts"
            affairs_config_root.mkdir(parents=True, exist_ok=True)
            output_root.mkdir(parents=True, exist_ok=True)

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

            blocked_receipt = output_root / "a010_blocked.json"
            blocked_receipt.write_text(
                json.dumps(
                    {
                        "result_code": "BLOCKED",
                        "message": "等待人工确认",
                        "output_payload": {
                            "artifacts": [],
                            "reason": "manual_gate",
                        },
                        "executor_meta": {
                            "requires_human": True,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            pass_receipt = output_root / "a020_pass.json"
            pass_receipt.write_text(
                json.dumps(
                    {
                        "result_code": "PASS",
                        "message": "执行完成",
                        "output_payload": {
                            "artifacts": [str(output_root / "done.txt")],
                        },
                        "executor_meta": {
                            "source": "unit-test",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

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
                        "project": {"project_name": "测试项目", "project_goal": "验证EA自动审计"},
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

            api.bootstrap_runtime(str(workspace_root))
            original_run_affair = api.run_affair

            def _fake_run_affair(
                affair_uid: str,
                *,
                config_path: str | Path | None = None,
                workspace_root: str | Path | None = None,
                config: dict | None = None,
            ):
                if affair_uid == "ar_A010_项目初始化":
                    return [blocked_receipt]
                if affair_uid == "ar_A020_文献导入与预处理":
                    return [pass_receipt]
                raise AssertionError(f"unexpected affair_uid: {affair_uid}")

            api.run_affair = _fake_run_affair
            try:
                result = api.run_project_mainflow(
                    project_config_path=str(project_config_path),
                    simulate=False,
                    ea_auto_audit_mode="on",
                    ea_auto_audit_policy="continue",
                )
            finally:
                api.run_affair = original_run_affair

        self.assertEqual(str(result.get("status") or ""), "completed")
        audit_events = [item for item in result.get("events") or [] if str(item.get("status") or "") == "ea_auto_audit"]
        self.assertEqual(len(audit_events), 1)
        self.assertEqual(str(audit_events[0].get("decision_action") or ""), "continue")

        request_statuses = {str(item.get("node_code") or ""): str(item.get("status") or "") for item in result.get("requests") or []}
        self.assertEqual(request_statuses.get("A010"), "已完成")
        self.assertEqual(request_statuses.get("A020"), "已完成")

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

    def test_schedulable_requests_should_support_age_boost_policy(self) -> None:
        """调度排序应支持年龄加权，避免老请求饥饿。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            workspace_root = runtime_root / "workspace"
            config_dir = workspace_root / "config" / "affairs_config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "A010.json"
            config_path.write_text("{}", encoding="utf-8")

            api.bootstrap_runtime(str(workspace_root))

            older = api.create_task_request(
                request_type="事务执行",
                target_affair_uid="ar_A010_项目初始化",
                node_code="A010",
                config_path=str(config_path),
                priority_score=1.0,
            )
            newer = api.create_task_request(
                request_type="事务执行",
                target_affair_uid="ar_A010_项目初始化",
                node_code="A010",
                config_path=str(config_path),
                priority_score=99.0,
            )

            files = get_runtime_store_files()
            with closing(sqlite3.connect(str(files["tasks_db"]))) as connection, connection:
                connection.execute(
                    'UPDATE "事务请求" SET "创建时间"=?, "更新时间"=? WHERE uid_请求=?',
                    ("2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00", str(older["request_uid"])),
                )

            rows = api.list_schedulable_task_requests(
                limit=2,
                scheduling_policy={
                    "weights": {
                        "priority": 0.05,
                        "age": 0.90,
                        "retry_penalty": 0.03,
                        "source_penalty": 0.02,
                    },
                    "age_cap_minutes": 30,
                },
            )

        self.assertEqual(len(rows), 2)
        self.assertEqual(str(rows[0]["request_uid"]), str(older["request_uid"]))
        self.assertIn("schedule_score", rows[0])
        self.assertIn("schedule_breakdown", rows[0])
        self.assertNotEqual(str(rows[1]["request_uid"]), str(older["request_uid"]))
        self.assertEqual(str(rows[1]["request_uid"]), str(newer["request_uid"]))

    def test_run_scheduler_cycle_should_execute_global_pending_requests(self) -> None:
        """全局调度循环应能消费待调度请求。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / "workspace"
            config_dir = workspace_root / "config" / "affairs_config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "A010.json"
            config_path.write_text("{}", encoding="utf-8")

            api.bootstrap_runtime(str(workspace_root))

            request = api.create_task_request(
                request_type="事务执行",
                target_affair_uid="ar_A010_项目初始化",
                node_code="A010",
                config_path=str(config_path),
                payload={"workspace_root": str(workspace_root)},
            )

            original_run_affair = api.run_affair

            def _fake_run_affair(
                affair_uid: str,
                *,
                config_path: str | Path | None = None,
                workspace_root: str | Path | None = None,
                config: dict | None = None,
            ):
                self.assertEqual(affair_uid, "ar_A010_项目初始化")
                self.assertTrue(Path(str(config_path)).exists())
                self.assertEqual(Path(str(workspace_root)).resolve(), expected_workspace.resolve())
                return [expected_workspace / "workspace" / "artifacts" / "ok.txt"]

            expected_workspace = workspace_root
            api.run_affair = _fake_run_affair
            try:
                events = api.run_scheduler_cycle(max_requests=1)
            finally:
                api.run_affair = original_run_affair

            refreshed = api.get_task_request(str(request["request_uid"]))

        self.assertEqual(len(events), 1)
        self.assertEqual(str(events[0].get("status") or ""), "completed")
        self.assertEqual(str(refreshed.get("status") or ""), "已完成")

    def test_run_aoe_control_loop_should_stop_after_idle(self) -> None:
        """控制循环应能消费请求并在连续空闲后停机。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / "workspace"
            config_dir = workspace_root / "config" / "affairs_config"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "A010.json"
            config_path.write_text("{}", encoding="utf-8")

            api.bootstrap_runtime(str(workspace_root))

            request = api.create_task_request(
                request_type="事务执行",
                target_affair_uid="ar_A010_项目初始化",
                node_code="A010",
                config_path=str(config_path),
                payload={"workspace_root": str(workspace_root)},
            )

            original_run_affair = api.run_affair

            def _fake_run_affair(
                affair_uid: str,
                *,
                config_path: str | Path | None = None,
                workspace_root: str | Path | None = None,
                config: dict | None = None,
            ):
                self.assertEqual(affair_uid, "ar_A010_项目初始化")
                self.assertTrue(Path(str(config_path)).exists())
                self.assertEqual(Path(str(workspace_root)).resolve(), expected_workspace.resolve())
                return [expected_workspace / "workspace" / "artifacts" / "ok.txt"]

            expected_workspace = workspace_root
            api.run_affair = _fake_run_affair
            try:
                payload = api.run_aoe_control_loop(
                    max_cycles=5,
                    max_requests_per_cycle=1,
                    stop_when_idle=True,
                    max_idle_cycles=1,
                    idle_sleep_seconds=0.0,
                )
            finally:
                api.run_affair = original_run_affair

            refreshed = api.get_task_request(str(request["request_uid"]))

        self.assertEqual(str(payload.get("status") or ""), "stopped_idle")
        self.assertEqual(str(payload.get("stop_reason") or ""), "idle_stop")
        self.assertGreaterEqual(int(payload.get("cycle_count") or 0), 2)
        self.assertGreaterEqual(int(payload.get("total_events") or 0), 1)
        self.assertEqual(str(refreshed.get("status") or ""), "已完成")

    def test_run_aoe_control_loop_should_validate_cycle_count(self) -> None:
        """控制循环应拒绝无效拍次数。"""

        with self.assertRaises(ValueError):
            api.run_aoe_control_loop(max_cycles=0)

if __name__ == "__main__":
    unittest.main()