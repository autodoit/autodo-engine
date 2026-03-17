"""result_protocol 单元测试。"""

from __future__ import annotations

import unittest

from autodoengine.core.enums import BlockReasonCode, BlockScope, ResultCode
from autodoengine.core.errors import ReceiptProtocolError
from autodoengine.core.types import NodeContext, ResultReceipt
from autodoengine.scheduling.result_protocol import (
    build_blocked_receipt,
    build_pass_receipt,
    normalize_receipt,
    validate_receipt,
)


class TestResultProtocol(unittest.TestCase):
    """回执协议测试。"""

    def test_build_pass_receipt(self) -> None:
        """PASS 回执构造应成功。"""

        receipt = build_pass_receipt(output_payload={"ok": True}, evidence=["e1"])
        self.assertEqual(receipt.result_code, ResultCode.PASS)
        self.assertEqual(receipt.output_payload.get("ok"), True)

    def test_validate_blocked_missing_reason(self) -> None:
        """BLOCKED 缺少 reason 应报错。"""

        receipt = ResultReceipt(result_code=ResultCode.BLOCKED)
        with self.assertRaises(ReceiptProtocolError):
            validate_receipt(receipt)

    def test_normalize_from_dict(self) -> None:
        """字典回执应被标准化。"""

        node_context = NodeContext(
            node_uid="node-1",
            node_type="process",
            affair_uid="affair-1",
            risk_level="normal",
            policies={},
        )
        receipt = normalize_receipt(
            {
                "result_code": "BLOCKED",
                "block_reason_code": "dependency_unready",
                "block_scope": "affair",
                "requires_human": False,
            },
            node_context=node_context,
        )
        self.assertEqual(receipt.result_code, ResultCode.BLOCKED)
        self.assertEqual(receipt.block_reason_code, BlockReasonCode.DEPENDENCY_UNREADY)
        self.assertEqual(receipt.block_scope, BlockScope.AFFAIR)
        self.assertEqual(receipt.aa_handling_mode, "preset_script")
        self.assertIsNone(receipt.fallback_reason_code)
        self.assertEqual(receipt.fallback_attempt, 0)

    def test_normalize_with_fallback_fields(self) -> None:
        """字典回执应正确携带 fallback 字段。"""

        node_context = NodeContext(
            node_uid="node-1",
            node_type="process",
            affair_uid="affair-1",
            risk_level="normal",
            policies={},
        )
        receipt = normalize_receipt(
            {
                "result_code": "PASS",
                "aa_handling_mode": "llm_fallback",
                "fallback_reason_code": "script_exception",
                "fallback_attempt": 1,
            },
            node_context=node_context,
        )
        self.assertEqual(receipt.result_code, ResultCode.PASS)
        self.assertEqual(receipt.aa_handling_mode, "llm_fallback")
        self.assertEqual(receipt.fallback_reason_code, "script_exception")
        self.assertEqual(receipt.fallback_attempt, 1)

    def test_build_blocked_receipt(self) -> None:
        """BLOCKED 构造器应返回完整对象。"""

        receipt = build_blocked_receipt(
            reason_code=BlockReasonCode.HUMAN_CONFIRMATION_REQUIRED,
            block_scope=BlockScope.NODE,
            requires_human=True,
            message="需要人工确认",
        )
        self.assertTrue(receipt.requires_human)
        self.assertEqual(receipt.block_scope, BlockScope.NODE)


if __name__ == "__main__":
    unittest.main()

