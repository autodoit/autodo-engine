"""replay_engine 迁移后行为测试（P2-C 救活验证）。

验证：结果码→中文步骤状态映射、未知码回退阻断、按 task_uid 取最近一条、缺文件返回空。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autodoengine.taskdb.replay_engine import ReplayEngine, status_from_result_code


class TestReplayEngine(unittest.TestCase):
    def test_status_from_result_code(self) -> None:
        """结果码应映射到中文步骤状态，未知码回退为阻断。"""

        self.assertEqual(status_from_result_code("PASS"), "通过")
        self.assertEqual(status_from_result_code("BLOCKED"), "阻断")
        self.assertEqual(status_from_result_code("nonsense"), "阻断")

    def test_replay_latest_per_task(self) -> None:
        """同一 task_uid 多条记录时取最后一条状态。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            log = Path(temp_dir) / "run.jsonl"
            rows = [
                {"task_uid": "t1", "transaction_uid": "x1", "result_code": "PASS"},
                {"task_uid": "t1", "transaction_uid": "x2", "result_code": "RETRY"},
                {"task_uid": "t2", "transaction_uid": "x3", "result_code": "BACKTRACK"},
            ]
            log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            state = ReplayEngine(execution_log_path=log).replay()

        self.assertEqual(state["t1"]["last_transaction_uid"], "x2")
        self.assertEqual(state["t1"]["step_status"], "重试")
        self.assertEqual(state["t2"]["step_status"], "回退")

    def test_replay_missing_file_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = ReplayEngine(execution_log_path=Path(temp_dir) / "nope.jsonl")
            self.assertEqual(engine.replay(), {})


if __name__ == "__main__":
    unittest.main()
