"""engine 独立运行模式测试。"""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autodoengine import api
from autodoengine.utils.common import affair_sync


class TestEngineStandaloneMode(unittest.TestCase):
    """验证 engine 在未安装 autodo-kit 时的回退能力。"""

    def test_default_aok_affairs_root_fallback_to_engine(self) -> None:
        """未安装 autodokit 时应回退到 autodoengine/affairs。

        Returns:
            None。
        """

        with mock.patch("importlib.util.find_spec", return_value=None):
            root = affair_sync.default_aok_affairs_root()
        self.assertTrue(str(root).replace("\\", "/").endswith("autodoengine/affairs"))
        self.assertTrue(root.exists())

    def test_load_tools_module_fallback_to_engine_tools(self) -> None:
        """当 autodokit.tools 不可导入时应回退到 autodoengine.tools。

        Returns:
            None。
        """

        real_import_module = importlib.import_module

        def _fake_import_module(name: str):
            if name == "autodokit.tools":
                raise ModuleNotFoundError("autodokit.tools missing")
            return real_import_module(name)

        with mock.patch("importlib.import_module", side_effect=_fake_import_module):
            module = api._load_tools_module()

        self.assertEqual(module.__name__, "autodoengine.tools")
        self.assertTrue(hasattr(module, "list_user_tools"))

    def test_run_builtin_start_affair_success(self) -> None:
        """内置图节点_start 事务应可执行并产出结果文件。

        Returns:
            None。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            outputs = api.run_affair(
                "图节点_start",
                config={"output_dir": str(workspace / "output" / "demo")},
                workspace_root=workspace,
                strict=False,
            )

            self.assertTrue(outputs)
            self.assertTrue(Path(outputs[0]).exists())

    def test_public_api_should_accept_chinese_keyword_arguments(self) -> None:
        """AOE 公共 API 应支持中文关键字参数。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            api.bootstrap_runtime(运行时根目录=str(workspace))

            prepared = api.prepare_affair_config(
                配置={"output_dir": "output/demo"},
                工作区根路径=workspace,
            )
            self.assertTrue(Path(prepared["output_dir"]).is_absolute())

            module = api.import_affair_module(
                事务唯一标识="图节点_start",
                工作区根路径=workspace,
                严格模式=False,
            )
            self.assertTrue(hasattr(module, "execute"))

            outputs = api.run_affair(
                事务唯一标识="图节点_start",
                配置={"output_dir": str(workspace / "output" / "demo")},
                工作区根路径=workspace,
                严格模式=False,
            )
            self.assertTrue(outputs)
            self.assertTrue(Path(outputs[0]).exists())

            summary = api.refresh_affair_registry(工作区根路径=workspace, 严格模式=False)
            self.assertIn("stats", summary)

            rows = api.list_runtime_affairs(工作区根路径=workspace, 严格模式=False)
            self.assertIsInstance(rows, list)

            conflicts = api.check_affair_conflicts(工作区根路径=workspace)
            self.assertIn("errors", conflicts)

            registry_paths = api.get_affair_registry_paths(工作区根路径=workspace)
            self.assertIsInstance(registry_paths, dict)
            self.assertTrue(registry_paths)


if __name__ == "__main__":
    unittest.main()
