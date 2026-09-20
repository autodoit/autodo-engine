"""P1 契约归一测试：中文主契约 config/注册表/流程图可读、重复 node_code 报错。

对应设计基准 O5 与验收 F6：宿主按中文主契约写 config.json，引擎主入口
归一化后仍应正确解析；注册表出现重复节点编码时须显式报错而非静默 last-wins。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoengine import api
from autodoengine.utils.config_normalizer import normalize_to_legacy_view


class TestNormalizeProjectConfig(unittest.TestCase):
    def test_chinese_block_maps_to_english_view(self) -> None:
        """中文主契约块应归一为英文内部契约视图。"""

        raw = {
            "工作区根路径": "/tmp/ws",
            "运行时": {"流程图路径": "g.json", "开始节点": "A010"},
            "路径": {"事务入口注册表路径": "reg.json"},
            "节点输入": {"A010": "a010.json"},
        }
        cfg = normalize_to_legacy_view(raw)
        self.assertEqual(cfg["workspace_root"], "/tmp/ws")
        self.assertEqual(cfg["runtime"]["workflow_graph_path"], "g.json")
        self.assertEqual(cfg["runtime"]["start_node"], "A010")
        self.assertEqual(cfg["paths"]["affair_entry_registry_path"], "reg.json")
        self.assertEqual(cfg["node_inputs"], {"A010": "a010.json"})

    def test_english_config_passthrough(self) -> None:
        """已是英文契约的配置应原样保留（归一为幂等）。"""

        raw = {"runtime": {"workflow_graph_path": "g.json"}, "workspace_root": "/tmp/ws"}
        cfg = normalize_to_legacy_view(raw)
        self.assertEqual(cfg, raw)

    def test_non_mapping_returns_empty(self) -> None:
        self.assertEqual(normalize_to_legacy_view(None), {})
        self.assertEqual(normalize_to_legacy_view([1, 2]), {})


def _write_mainflow_tree(root: Path, *, chinese_project_config: bool, duplicate_node_code: bool) -> Path:
    """构造一棵最小主链工程目录，返回项目 config.json 路径。

    流程图与注册表始终用英文键（与真实 AOK/ARK 注册表一致）；
    仅项目 config.json 可选用中文主契约键，用来验证归一化。
    """

    project_root = root / "project"
    workspace_root = project_root / "workspace"
    config_root = workspace_root / "config"
    affairs_config_root = config_root / "affairs_config"
    affairs_config_root.mkdir(parents=True, exist_ok=True)

    graph_path = project_root / ".autodoengine" / "workflows" / "demo" / "graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps({"nodes": [{"node_uid": "n_A010", "enabled": True}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    a010_config = affairs_config_root / "A010.json"
    a010_config.write_text("{}", encoding="utf-8")

    registry_records = [
        {"node_code": "A010", "affair_uid": "ar_A010_x", "config_path": str(a010_config), "implemented": True}
    ]
    if duplicate_node_code:
        registry_records.append(
            {"node_code": "A010", "affair_uid": "ar_A010_dup", "config_path": str(a010_config), "implemented": True}
        )
    registry_path = config_root / "affair_entry_registry.json"
    registry_path.write_text(
        json.dumps({"records": registry_records}, ensure_ascii=False), encoding="utf-8"
    )

    action_routing = {
        "execute": "aoe.run", "continue": "aoe.resume", "pause": "aoe.pause",
        "retry": "aoe.retry_current", "fallback": "aoe.fallback_current",
        "stop": "aoe.stop", "gate_pass": "aoe.gate_pass",
    }
    if chinese_project_config:
        project_config = {
            "工作流名称": "中文契约项目",
            "工作区根路径": str(workspace_root),
            "项目": {"项目名称": "中文契约项目", "项目目标": "验证归一化"},
            "运行时": {
                "流程图路径": str(graph_path),
                "开始节点": "A010",
                "结束节点": "A010",
                "用户动作路由": action_routing,
            },
            "路径": {"事务入口注册表路径": str(registry_path)},
            "节点输入": {"A010": str(a010_config)},
        }
    else:
        project_config = {
            "workflow_name": "英文契约项目",
            "workspace_root": str(workspace_root),
            "runtime": {
                "workflow_graph_path": str(graph_path),
                "start_node": "A010",
                "end_node": "A010",
                "user_action_routing": action_routing,
            },
            "paths": {"affair_entry_registry_path": str(registry_path)},
            "node_inputs": {"A010": str(a010_config)},
        }
    project_config_path = config_root / "config.json"
    project_config_path.write_text(json.dumps(project_config, ensure_ascii=False), encoding="utf-8")
    return project_config_path


class TestMainflowConsumesNormalizedConfig(unittest.TestCase):
    def test_chinese_keyed_config_runs_mainflow(self) -> None:
        """中文主契约配置经归一化后应能完整解析并模拟跑通主链。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg_path = _write_mainflow_tree(
                Path(temp_dir), chinese_project_config=True, duplicate_node_code=False
            )
            result = api.run_project_mainflow(project_config_path=str(cfg_path), simulate=True)
        self.assertEqual(result["validate"]["ok"], True)
        self.assertEqual([item["node_code"] for item in result["events"]], ["A010"])

    def test_duplicate_node_code_raises(self) -> None:
        """注册表重复 node_code 应显式报错，而非静默覆盖。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg_path = _write_mainflow_tree(
                Path(temp_dir), chinese_project_config=False, duplicate_node_code=True
            )
            with self.assertRaises(ValueError) as ctx:
                api.validate_project_mainflow(project_config_path=str(cfg_path))
        self.assertIn("A010", str(ctx.exception))
        self.assertIn("重复 node_code", str(ctx.exception))

    def test_chinese_keyed_graph_and_registry_resolve(self) -> None:
        """流程图与注册表也用中文主契约时（ARK 真实形态），主链仍须解析出全部节点。

        回归动因：真实 ARK 的 graph/registry 以 `节点/节点唯一标识/记录/节点编码` 书写，
        reader 若只归一化 config 而裸读英文键，会得到 0 节点、空注册表。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            config_root = workspace / "config"
            affairs_root = config_root / "affairs_config"
            affairs_root.mkdir(parents=True, exist_ok=True)

            affair_config = affairs_root / "A010.json"
            affair_config.write_text("{}", encoding="utf-8")

            graph = {
                "流程图唯一标识": "g-cn",
                "流程图名称": "中文契约图",
                "流程图版本": "3.0.0",
                "节点": [
                    {"节点唯一标识": "n_a010", "节点类型": "开始", "事务唯一标识": "ar_A010_x", "是否启用": True},
                    {"节点唯一标识": "n_a020", "节点类型": "结束", "事务唯一标识": "ar_A020_x", "是否启用": True},
                ],
                "边": [
                    {
                        "边唯一标识": "e_010_020",
                        "起点节点唯一标识": "n_a010",
                        "终点节点唯一标识": "n_a020",
                        "条件表达式": "always",
                        "是否启用": True,
                    }
                ],
            }
            graph_path = root / "graph.json"
            graph_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")

            affair_config_020 = affairs_root / "A020.json"
            affair_config_020.write_text("{}", encoding="utf-8")
            registry = {
                "契约版本": "cn-entry-v1",
                "记录": [
                    {
                        "节点编码": "A010",
                        "节点名称": "初始化",
                        "事务唯一标识": "ar_A010_x",
                        "模块路径": "autodokit.affairs.demo.affair",
                        "入口函数": "execute",
                        "是否已实现": True,
                        "配置路径": str(affair_config),
                    },
                    {
                        "节点编码": "A020",
                        "节点名称": "收尾",
                        "事务唯一标识": "ar_A020_x",
                        "模块路径": "autodokit.affairs.demo.affair",
                        "入口函数": "execute",
                        "是否已实现": True,
                        "配置路径": str(affair_config_020),
                    },
                ],
            }
            registry_path = config_root / "affair_entry_registry.json"
            registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

            action_routing = {
                key: f"aoe.{key}"
                for key in ("execute", "continue", "pause", "retry", "fallback", "stop", "gate_pass")
            }
            project_config = {
                "工作区根路径": str(workspace),
                "运行时": {
                    "流程图路径": str(graph_path),
                    "开始节点": "A010",
                    "结束节点": "A020",
                    "用户动作路由": action_routing,
                },
                "路径": {"事务入口注册表路径": "config/affair_entry_registry.json"},
                "节点输入": {"A010": "config/affairs_config/A010.json", "A020": "config/affairs_config/A020.json"},
            }
            config_path = config_root / "config.json"
            config_path.write_text(json.dumps(project_config, ensure_ascii=False), encoding="utf-8")

            result = api.validate_project_mainflow(project_config_path=str(config_path))

        self.assertTrue(result["ok"], msg=str(result))
        self.assertEqual(result["node_count"], 2)
        self.assertEqual(result["target_nodes"], ["A010", "A020"])


if __name__ == "__main__":
    unittest.main()
