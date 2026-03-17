"""事务回执统一协议。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from autodoengine.core.enums import BlockReasonCode, BlockScope, ResultCode
from autodoengine.core.errors import ReceiptProtocolError
from autodoengine.core.types import NodeContext, ResultReceipt


def normalize_receipt(raw_result: Any, *, node_context: NodeContext) -> ResultReceipt:
    """把事务原始结果规范化为统一回执。"""

    if isinstance(raw_result, ResultReceipt):
        validate_receipt(raw_result)
        return raw_result

    if isinstance(raw_result, dict):
        receipt = ResultReceipt(
            result_code=ResultCode(str(raw_result.get("result_code", ResultCode.PASS.value))),
            block_reason_code=(
                BlockReasonCode(str(raw_result["block_reason_code"]))
                if raw_result.get("block_reason_code")
                else None
            ),
            block_scope=(BlockScope(str(raw_result["block_scope"])) if raw_result.get("block_scope") else None),
            retryable=bool(raw_result.get("retryable", False)),
            requires_human=bool(raw_result.get("requires_human", False)),
            output_payload=dict(raw_result.get("output_payload") or {}),
            evidence=list(raw_result.get("evidence") or []),
            message=str(raw_result.get("message") or ""),
            executor_meta=dict(raw_result.get("executor_meta") or {}),
            aa_handling_mode=str(raw_result.get("aa_handling_mode") or "preset_script"),
            fallback_reason_code=(
                str(raw_result.get("fallback_reason_code"))
                if raw_result.get("fallback_reason_code") is not None
                else None
            ),
            fallback_attempt=int(raw_result.get("fallback_attempt") or 0),
        )
        validate_receipt(receipt)
        return receipt

    return build_blocked_receipt(
        reason_code=BlockReasonCode.GOAL_AMBIGUOUS,
        block_scope=BlockScope.AFFAIR,
        requires_human=True,
        message=f"无法解析事务返回值，节点：{node_context.node_uid}",
    )


def validate_receipt(receipt: ResultReceipt) -> None:
    """校验回执协议是否合法。"""

    if receipt.result_code == ResultCode.BLOCKED and receipt.block_reason_code is None:
        raise ReceiptProtocolError("BLOCKED 回执必须包含 block_reason_code")


def build_pass_receipt(*, output_payload: dict[str, Any], evidence: list[str]) -> ResultReceipt:
    """构造 PASS 回执。"""

    return ResultReceipt(
        result_code=ResultCode.PASS,
        output_payload=output_payload,
        evidence=evidence,
    )


def build_retry_receipt(*, message: str, retryable: bool, evidence: list[str]) -> ResultReceipt:
    """构造 RETRY 回执。"""

    return ResultReceipt(
        result_code=ResultCode.RETRY,
        message=message,
        retryable=retryable,
        evidence=evidence,
    )


def build_backtrack_receipt(*, message: str, evidence: list[str]) -> ResultReceipt:
    """构造 BACKTRACK 回执。"""

    return ResultReceipt(
        result_code=ResultCode.BACKTRACK,
        message=message,
        evidence=evidence,
    )


def build_blocked_receipt(
    *,
    reason_code: BlockReasonCode,
    block_scope: BlockScope,
    requires_human: bool,
    message: str,
) -> ResultReceipt:
    """构造 BLOCKED 回执。"""

    return ResultReceipt(
        result_code=ResultCode.BLOCKED,
        block_reason_code=reason_code,
        block_scope=block_scope,
        requires_human=requires_human,
        retryable=False,
        message=message,
        aa_handling_mode="preset_script",
        fallback_reason_code=None,
        fallback_attempt=0,
    )


def receipt_to_dict(receipt: ResultReceipt) -> dict[str, Any]:
    """将回执转换为字典。"""

    payload = asdict(receipt)
    payload["result_code"] = receipt.result_code.value
    payload["block_reason_code"] = receipt.block_reason_code.value if receipt.block_reason_code else None
    payload["block_scope"] = receipt.block_scope.value if receipt.block_scope else None
    payload["aa_handling_mode"] = receipt.aa_handling_mode
    payload["fallback_reason_code"] = receipt.fallback_reason_code
    payload["fallback_attempt"] = receipt.fallback_attempt
    return payload

