"""事务管理系统测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()

