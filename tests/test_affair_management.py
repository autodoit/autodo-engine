"""事务管理系统测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoengine.api import import_user_affair
from autodoengine.utils.affair_registry import build_registry
from autodoengine.utils.common.affair_sync import build_runtime_registry, sync_affair_databases


class TestAffairManagement(unittest.TestCase):
    """事务管理系统核心行为测试。"""

    def _write_user_affair(
        self,
        *,
        workspace_root: Path,
        affair_uid: str,
        domain: str,
    ) -> None:
        """写入一个用户事务样例。

        Args:
            workspace_root: 用户工作区根目录。
            affair_uid: 事务 UID。
            domain: 事务域。

        Returns:
            None。
        """

        affair_dir = workspace_root / ".autodokit" / "affairs" / affair_uid
        affair_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "name": affair_uid,
            "domain": domain,
            "owner": "user",
            "version": "1.0.0",
            "runner": {
                "module": "autodoengine.affairs.图节点_start.affair",
                "callable": "execute",
                "pass_mode": "config_path",
                "kwargs": {},
            },
            "docs": {
                "md_path": "",
            },
        }
        (affair_dir / "affair.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (affair_dir / "affair.py").write_text("def execute(config_path, **kwargs):\n    return {}\n", encoding="utf-8")
        (affair_dir / "affair.md").write_text("# 示例事务\n", encoding="utf-8")

    def _write_pure_user_affair(self, *, workspace_root: Path, affair_name: str) -> None:
        """写入纯三件套用户事务样例。

        Args:
            workspace_root: 用户工作区根目录。
            affair_name: 事务目录名。

        Returns:
            None。
        """

        affair_dir = workspace_root / ".autodokit" / "affairs" / affair_name
        affair_dir.mkdir(parents=True, exist_ok=True)
        (affair_dir / "affair.py").write_text(
            "def execute(config_path, **kwargs):\n    return [config_path]\n",
            encoding="utf-8",
        )
        (affair_dir / "affair.json").write_text(json.dumps({"input_path": "./input"}, ensure_ascii=False, indent=2), encoding="utf-8")
        (affair_dir / "affair.md").write_text("# 纯事务\n\n用于测试。\n", encoding="utf-8")

    def test_sync_official_registry_success(self) -> None:
        """官方事务库可成功同步并产出统计。"""

        result = sync_affair_databases(workspace_root=None, strict=False)
        self.assertGreater(len(result.records), 0)
        self.assertIn("aok_graph", result.stats)
        self.assertIn("aok_business", result.stats)

    def test_user_graph_domain_rejected(self) -> None:
        """用户声明 graph 域事务会被拒绝进入运行时视图。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            self._write_user_affair(workspace_root=workspace, affair_uid="用户图节点示例", domain="graph")

            result = sync_affair_databases(workspace_root=workspace, strict=False)

        self.assertTrue(any("仅允许 business 域" in item for item in result.errors))
        self.assertNotIn("用户图节点示例", {str(item.get("affair_uid")) for item in result.records})

    def test_user_override_aok_business_with_warning(self) -> None:
        """用户可覆盖官方 business 事务并产生警告。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            self._write_user_affair(workspace_root=workspace, affair_uid="CAJ文件转PDF", domain="business")

            result = sync_affair_databases(workspace_root=workspace, strict=False)
            runtime_registry = build_runtime_registry(workspace_root=workspace, strict=False)

        self.assertTrue(any("覆盖官方 business" in item for item in result.warnings))
        self.assertIn("CAJ文件转PDF", runtime_registry)
        self.assertEqual(str(runtime_registry["CAJ文件转PDF"].get("owner")), "user")

    def test_build_registry_uses_workspace_overlay(self) -> None:
        """build_registry 在传 workspace_root 时可读取用户覆盖后的运行时视图。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            self._write_user_affair(workspace_root=workspace, affair_uid="CAJ文件转PDF", domain="business")
            registry = build_registry(strict=False, workspace_root=workspace)

        self.assertIn("CAJ文件转PDF", registry)
        self.assertEqual(str(registry["CAJ文件转PDF"].get("owner")), "user")

    def test_pure_triplet_affair_sync_success(self) -> None:
        """纯三件套事务可被同步并产出新版字段。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            self._write_pure_user_affair(workspace_root=workspace, affair_name="纯事务示例")

            result = sync_affair_databases(workspace_root=workspace, strict=False)
            target = next(item for item in result.records if str(item.get("affair_uid")) == "纯事务示例")

        self.assertEqual(str(target.get("display_name")), "纯事务示例")
        self.assertEqual(str(target.get("folder_name")), "纯事务示例")
        self.assertIn("source_py_path", target)
        self.assertIn("params_json_path", target)
        self.assertIn("doc_md_path", target)
        self.assertIn("record_uid", target)
        self.assertEqual(str(target.get("owner")), "user")

    def test_import_user_affair_auto_rename(self) -> None:
        """导入同名事务时应自动追加 _v正整数 后缀。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source_py = workspace / "demo_affair.py"
            source_json = workspace / "demo_affair.json"
            source_md = workspace / "demo_affair.md"

            source_py.write_text("def execute(config_path, **kwargs):\n    return [config_path]\n", encoding="utf-8")
            source_json.write_text(json.dumps({"x": 1}, ensure_ascii=False, indent=2), encoding="utf-8")
            source_md.write_text("# demo\n", encoding="utf-8")

            first = import_user_affair(
                source_py_path=source_py,
                source_params_json_path=source_json,
                source_doc_md_path=source_md,
                affair_name="导入事务",
                workspace_root=workspace,
                strict=False,
            )

            second = import_user_affair(
                source_py_path=source_py,
                source_params_json_path=source_json,
                source_doc_md_path=source_md,
                affair_name="导入事务",
                workspace_root=workspace,
                strict=False,
            )

        self.assertEqual(str(first.get("final_name")), "导入事务")
        self.assertEqual(str(second.get("final_name")), "导入事务_v2")
        self.assertTrue(bool(second.get("renamed")))


if __name__ == "__main__":
    unittest.main()

