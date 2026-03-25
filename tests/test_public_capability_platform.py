"""public capability 平台回归测试。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from autodoengine import api
from autodoengine.tools.adapters.runner import run_capability_from_params_file


class TestPublicCapabilityPlatform(unittest.TestCase):
    """验证 capability manifest、facade、多入口与事务编排。"""

    def test_lint_capabilities_passes(self) -> None:
        """manifest/schema/实现一致性校验应通过。

        Returns:
            None。
        """

        report = api.lint_capabilities()
        self.assertTrue(bool(report.get("passed")))
        self.assertGreaterEqual(int(report.get("capability_count") or 0), 10)

    def test_invoke_capability_python_success(self) -> None:
        """Python API 可成功执行 capability 并落盘审计。

        Returns:
            None。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            result = api.invoke_capability(
                "affair_show_paths",
                payload={"workspace_root": str(workspace)},
                caller_context={"caller_source": "pytest"},
                workspace_root=workspace,
            )

            self.assertEqual(str(result.get("status")), "success")
            self.assertTrue(Path(str(result.get("audit_path") or "")).exists())
            self.assertIn("aok_db_path", dict(result.get("data") or {}))

    def test_runner_adapter_matches_python_entry(self) -> None:
        """Runner 参数文件入口与 Python 入口应返回同一 capability 成功状态。

        Returns:
            None。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            params_path = workspace / "params.json"
            params_path.write_text(
                json.dumps(
                    {
                        "capability_id": "affair_refresh",
                        "payload": {"workspace_root": str(workspace), "strict": False},
                        "caller_context": {"caller_source": "pytest-runner"},
                        "workspace_root": str(workspace),
                        "allow_internal": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            python_result = api.invoke_capability(
                "affair_refresh",
                payload={"workspace_root": str(workspace), "strict": False},
                caller_context={"caller_source": "pytest-python"},
                workspace_root=workspace,
            )
            runner_result = run_capability_from_params_file(params_path)

            self.assertEqual(str(python_result.get("status")), "success")
            self.assertEqual(str(runner_result.get("status")), "success")
            self.assertEqual(
                int(dict(python_result.get("data") or {}).get("record_count") or 0),
                int(dict(runner_result.get("data") or {}).get("record_count") or 0),
            )

    def test_cli_invoke_capability_success(self) -> None:
        """CLI 入口应可调用 capability。

        Returns:
            None。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            payload_json = json.dumps({"workspace_root": str(workspace)}, ensure_ascii=False)
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "autodoengine.main",
                    "invoke-capability",
                    "--capability-id",
                    "affair_show_paths",
                    "--payload-json",
                    payload_json,
                    "--workspace-root",
                    str(workspace),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, msg=process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(str(result.get("status")), "success")
            self.assertIn("aok_db_path", dict(result.get("data") or {}))

    def test_composite_affairs_success(self) -> None:
        """两个复合事务链路应可执行并产出结果文件。

        Returns:
            None。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            inspection_outputs = api.run_affair(
                "引擎能力巡检",
                config={"output_dir": str(workspace / "inspection")},
                workspace_root=workspace,
                strict=False,
            )
            probe_outputs = api.run_affair(
                "引擎运行时探针",
                config={
                    "runtime_base_dir": str(workspace / "runtime_probe"),
                    "output_dir": str(workspace / "probe"),
                },
                workspace_root=workspace,
                strict=False,
            )

            self.assertTrue(Path(inspection_outputs[0]).exists())
            self.assertTrue(Path(probe_outputs[0]).exists())


if __name__ == "__main__":
    unittest.main()
