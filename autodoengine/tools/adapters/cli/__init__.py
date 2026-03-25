"""CLI adapter。"""

from __future__ import annotations

import json
from typing import Any

from autodoengine.tools.public.facade import invoke_capability, list_capabilities
from autodoengine.tools.public.registry import lint_public_manifest


def register_cli_subcommands(subparsers: Any) -> None:
    """注册 capability CLI 子命令。

    Args:
        subparsers: argparse 子命令对象。
    """

    p_list = subparsers.add_parser("list-capabilities", help="列出 public capability 清单")
    p_list.add_argument("--include-internal", action="store_true", help="包含非 user 级 capability")

    p_invoke = subparsers.add_parser("invoke-capability", help="统一执行 capability")
    p_invoke.add_argument("--capability-id", required=True, help="capability 标识")
    p_invoke.add_argument("--payload-json", default="{}", help="JSON 字符串形式的 payload")
    p_invoke.add_argument("--workspace-root", default=None, help="工作区根目录")
    p_invoke.add_argument("--allow-internal", action="store_true", help="允许 developer/internal capability")

    subparsers.add_parser("lint-capabilities", help="校验 manifest/schema/实现一致性")


def handle_cli_command(args: Any) -> bool:
    """处理 capability 相关 CLI 命令。

    Args:
        args: argparse 结果对象。

    Returns:
        是否已处理当前命令。
    """

    if args.command == "list-capabilities":
        print(json.dumps(list_capabilities(include_internal=bool(args.include_internal)), ensure_ascii=False, indent=2))
        return True

    if args.command == "invoke-capability":
        payload = json.loads(str(args.payload_json or "{}"))
        result = invoke_capability(
            str(args.capability_id),
            payload=payload,
            caller_context={"caller_source": "autodoengine.main"},
            allow_internal=bool(args.allow_internal),
            workspace_root=args.workspace_root,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return True

    if args.command == "lint-capabilities":
        print(json.dumps(lint_public_manifest(), ensure_ascii=False, indent=2))
        return True

    return False
