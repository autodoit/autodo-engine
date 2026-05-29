"""v3 命令行入口。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from autodoengine import api
from autodoengine.taskdb import decision_store, log_store, task_store
from autodoengine.tools.adapters.cli import handle_cli_command, register_cli_subcommands


默认决策部门UID = "dept-default"


def _to_jsonable(value: object) -> object:
    """将 CLI 输出值转换为 JSON 兼容对象。"""

    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。"""

    parser = argparse.ArgumentParser(description="AOK v3 任务事务工作流 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-runtime", help="初始化运行时存储")
    p_init.add_argument("--base-dir", required=True, help="运行时根目录")

    p_register = sub.add_parser("register-graph", help="注册静态图")
    p_register.add_argument("--graph-file", required=True, help="图文件路径")

    p_create = sub.add_parser("create-task", help="创建任务")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--goal-text", required=True)
    p_create.add_argument("--current-node-uid", required=True)
    p_create.add_argument("--parent-task-uid", default=None)

    p_create_request = sub.add_parser("create-task-request", help="创建事务请求")
    p_create_request.add_argument("--request-type", required=True)
    p_create_request.add_argument("--target-affair-uid", required=True)
    p_create_request.add_argument("--task-uid", default=None)
    p_create_request.add_argument("--source-object-type", default="")
    p_create_request.add_argument("--source-object-uid", default="")
    p_create_request.add_argument("--node-code", default="")
    p_create_request.add_argument("--config-path", default="")
    p_create_request.add_argument("--priority-score", type=float, default=0.0)
    p_create_request.add_argument("--source", default="任务系统")
    p_create_request.add_argument("--request-contract-json", default="{}")
    p_create_request.add_argument("--payload-json", default="{}")
    p_create_request.add_argument("--metadata-json", default="{}")

    p_step = sub.add_parser("run-task-step", help="执行单步")
    p_step.add_argument("--task-uid", required=True)
    p_step.add_argument("--graph-uid", required=True)

    p_run = sub.add_parser("run-task", help="持续运行直到等待态")
    p_run.add_argument("--task-uid", required=True)
    p_run.add_argument("--graph-uid", required=True)
    p_run.add_argument("--max-steps", type=int, default=100)

    p_show_task = sub.add_parser("show-task", help="查看任务")
    p_show_task.add_argument("--task-uid", required=True)

    p_show_request = sub.add_parser("show-task-request", help="查看事务请求")
    p_show_request.add_argument("--request-uid", required=True)

    p_run_request = sub.add_parser("run-task-request", help="执行单个事务请求")
    p_run_request.add_argument("--request-uid", required=True)
    p_run_request.add_argument("--simulate", action="store_true", help="仅模拟执行，不真正调用事务")

    p_list_requests = sub.add_parser("list-task-requests", help="查看事务请求列表")
    p_list_requests.add_argument("--task-uid", default=None)
    p_list_requests.add_argument("--status", default=None)

    p_run_requests = sub.add_parser("run-task-requests", help="批量消费任务下待调度事务请求")
    p_run_requests.add_argument("--task-uid", required=True)
    p_run_requests.add_argument("--max-requests", type=int, default=100)
    p_run_requests.add_argument("--simulate", action="store_true", help="仅模拟执行，不真正调用事务")

    p_run_scheduler_cycle = sub.add_parser("run-scheduler-cycle", help="执行一轮全局请求调度")
    p_run_scheduler_cycle.add_argument("--max-requests", type=int, default=20)
    p_run_scheduler_cycle.add_argument("--simulate", action="store_true", help="仅模拟执行，不真正调用事务")
    p_run_scheduler_cycle.add_argument("--executor-uid", default="aoe-default-executor")
    p_run_scheduler_cycle.add_argument("--lease-seconds", type=int, default=120)
    p_run_scheduler_cycle.add_argument("--statuses-json", default="[]")
    p_run_scheduler_cycle.add_argument("--scheduling-policy-json", default="{}")

    p_run_control_loop = sub.add_parser("run-aoe-control-loop", help="执行多拍 AOE 控制循环")
    p_run_control_loop.add_argument("--max-cycles", type=int, default=1)
    p_run_control_loop.add_argument("--max-requests-per-cycle", type=int, default=20)
    p_run_control_loop.add_argument("--simulate", action="store_true", help="仅模拟执行，不真正调用事务")
    p_run_control_loop.add_argument("--executor-uid", default="aoe-default-executor")
    p_run_control_loop.add_argument("--lease-seconds", type=int, default=120)
    p_run_control_loop.add_argument("--statuses-json", default="[]")
    p_run_control_loop.add_argument("--scheduling-policy-json", default="{}")
    p_run_control_loop.add_argument("--stop-when-idle", action="store_true", help="持续空闲达到阈值后提前停止")
    p_run_control_loop.add_argument("--max-idle-cycles", type=int, default=3)
    p_run_control_loop.add_argument("--idle-sleep-seconds", type=float, default=1.0)

    p_validate_project = sub.add_parser("validate-project-mainflow", help="校验项目主链是否可由 AOE 正式运行")
    p_validate_project.add_argument("--project-config-path", required=True)
    p_validate_project.add_argument("--start-node", default=None)
    p_validate_project.add_argument("--end-node", default=None)

    p_run_project = sub.add_parser("run-project-mainflow", help="由 AOE 正式运行项目主链片段")
    p_run_project.add_argument("--project-config-path", required=True)
    p_run_project.add_argument("--start-node", default=None)
    p_run_project.add_argument("--end-node", default=None)
    p_run_project.add_argument("--simulate", action="store_true", help="仅模拟执行，不真正调用事务")
    p_run_project.add_argument("--source", default="项目经理")
    p_run_project.add_argument("--decision-department-uid", default=默认决策部门UID)
    p_run_project.add_argument(
        "--task-management-mode",
        default="simple",
        choices=["simple", "complex"],
        help="任务管理模式：simple=简单任务（默认），complex=复杂任务（实验）",
    )
    p_run_project.add_argument(
        "--ea-auto-audit-mode",
        default="auto",
        choices=["auto", "on", "off"],
        help="EA自动审计模式：auto跟随配置，on强制开启，off强制关闭",
    )
    p_run_project.add_argument(
        "--ea-auto-audit-policy",
        default=None,
        help="EA自动审计策略：llm_decide/continue/fail",
    )
    p_run_project.add_argument(
        "--ea-auto-audit-fail-action",
        default=None,
        help="EA自动审计调用失败动作：fail/blocked/continue",
    )
    p_run_project.add_argument(
        "--ea-auto-audit-model",
        default=None,
        help="EA自动审计模型覆盖（默认读取 config/决策部门）",
    )

    p_show_departments = sub.add_parser("show-decision-departments", help="查看决策部门列表")

    p_show_department_members = sub.add_parser("show-decision-department-members", help="查看决策部门成员")
    p_show_department_members.add_argument("--department-uid", default=默认决策部门UID)

    p_show_decisions = sub.add_parser("show-decisions", help="查看任务决策")
    p_show_decisions.add_argument("--task-uid", required=True)

    p_show_events = sub.add_parser("show-runtime-events", help="查看运行事件")
    p_show_events.add_argument("--task-uid", default=None)

    p_refresh_affairs = sub.add_parser("refresh-affair-registry", help="刷新事务数据库")
    p_refresh_affairs.add_argument("--workspace-root", default=None, help="用户工作区根目录")
    p_refresh_affairs.add_argument("--strict", action="store_true", help="严格模式（有错误即失败）")

    p_list_affairs = sub.add_parser("list-runtime-affairs", help="查看运行时事务列表")
    p_list_affairs.add_argument("--workspace-root", default=None, help="用户工作区根目录")
    p_list_affairs.add_argument("--strict", action="store_true", help="严格模式（有错误即失败）")

    p_check_conflicts = sub.add_parser("check-affair-conflicts", help="检查事务冲突与告警")
    p_check_conflicts.add_argument("--workspace-root", default=None, help="用户工作区根目录")

    p_show_runtime_paths = sub.add_parser("show-runtime-store-paths", help="查看当前运行时数据库路径")
    p_show_runtime_paths.add_argument("--base-dir", default=None, help="运行时根目录；不传时读取当前进程已初始化的运行时")

    p_show_affair_paths = sub.add_parser("show-affair-registry-paths", help="查看事务管理系统路径")
    p_show_affair_paths.add_argument("--workspace-root", default=None, help="用户工作区根目录")

    register_cli_subcommands(sub)

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """运行命令行入口。"""

    parser = build_parser()
    args = parser.parse_args(argv)

    if handle_cli_command(args):
        return 0

    if args.command == "init-runtime":
        api.bootstrap_runtime(args.base_dir)
        print(f"已初始化运行时：{Path(args.base_dir).resolve()}")
        return 0

    if args.command == "register-graph":
        graph = api.load_graph(args.graph_file)
        api.register_graph(graph)
        print(f"已注册图：{graph.graph_uid}")
        return 0

    if args.command == "create-task":
        task = api.create_task(
            title=args.title,
            goal_text=args.goal_text,
            current_node_uid=args.current_node_uid,
            parent_task_uid=args.parent_task_uid,
        )
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    if args.command == "create-task-request":
        payload = json.loads(args.payload_json or "{}")
        request_contract = json.loads(args.request_contract_json or "{}")
        metadata = json.loads(args.metadata_json or "{}")
        request = api.create_task_request(
            request_type=args.request_type,
            target_affair_uid=args.target_affair_uid,
            payload=payload if isinstance(payload, dict) else {},
            task_uid=args.task_uid,
            source_object_type=args.source_object_type,
            source_object_uid=args.source_object_uid,
            node_code=args.node_code,
            config_path=args.config_path,
            priority_score=args.priority_score,
            source=args.source,
            request_contract=request_contract if isinstance(request_contract, dict) else {},
            metadata=metadata if isinstance(metadata, dict) else {},
        )
        print(json.dumps(request, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-task-step":
        result = api.run_task_step(task_uid=args.task_uid, graph_uid=args.graph_uid)
        print(json.dumps(_to_jsonable(result), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "run-task":
        results = api.run_task_until_wait(
            task_uid=args.task_uid,
            graph_uid=args.graph_uid,
            max_steps=args.max_steps,
        )
        payload = [_to_jsonable(item) for item in results]
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "show-task":
        task = task_store.get_task(args.task_uid)
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    if args.command == "show-task-request":
        request = api.get_task_request(args.request_uid)
        print(json.dumps(request, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-task-request":
        payload = api.run_task_request(args.request_uid, simulate=bool(args.simulate))
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "list-task-requests":
        rows = api.list_task_requests(task_uid=args.task_uid, status=args.status)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-task-requests":
        payload = api.run_task_requests(
            task_uid=args.task_uid,
            max_requests=args.max_requests,
            simulate=bool(args.simulate),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "run-scheduler-cycle":
        statuses = json.loads(args.statuses_json or "[]")
        scheduling_policy = json.loads(args.scheduling_policy_json or "{}")
        payload = api.run_scheduler_cycle(
            max_requests=args.max_requests,
            simulate=bool(args.simulate),
            executor_uid=args.executor_uid,
            lease_seconds=args.lease_seconds,
            statuses=statuses if isinstance(statuses, list) else None,
            scheduling_policy=scheduling_policy if isinstance(scheduling_policy, dict) else None,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "run-aoe-control-loop":
        statuses = json.loads(args.statuses_json or "[]")
        scheduling_policy = json.loads(args.scheduling_policy_json or "{}")
        payload = api.run_aoe_control_loop(
            max_cycles=args.max_cycles,
            max_requests_per_cycle=args.max_requests_per_cycle,
            simulate=bool(args.simulate),
            executor_uid=args.executor_uid,
            lease_seconds=args.lease_seconds,
            statuses=statuses if isinstance(statuses, list) else None,
            scheduling_policy=scheduling_policy if isinstance(scheduling_policy, dict) else None,
            stop_when_idle=bool(args.stop_when_idle),
            max_idle_cycles=args.max_idle_cycles,
            idle_sleep_seconds=args.idle_sleep_seconds,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0 if str(payload.get("status") or "") in {"completed", "stopped_idle"} else 2

    if args.command == "validate-project-mainflow":
        payload = api.validate_project_mainflow(
            project_config_path=args.project_config_path,
            start_node=args.start_node,
            end_node=args.end_node,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0 if bool(payload.get("ok")) else 2

    if args.command == "run-project-mainflow":
        payload = api.run_project_mainflow(
            project_config_path=args.project_config_path,
            start_node=args.start_node,
            end_node=args.end_node,
            simulate=bool(args.simulate),
            source=args.source,
            decision_department_uid=args.decision_department_uid,
            task_management_mode=args.task_management_mode,
            ea_auto_audit_mode=args.ea_auto_audit_mode,
            ea_auto_audit_policy=args.ea_auto_audit_policy,
            ea_auto_audit_fail_action=args.ea_auto_audit_fail_action,
            ea_auto_audit_model=args.ea_auto_audit_model,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0 if str(payload.get("status") or "") in {"completed", "simulated"} else 2

    if args.command == "show-decision-departments":
        rows = api.list_decision_departments()
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.command == "show-decision-department-members":
        rows = api.list_decision_department_members(args.department_uid)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.command == "show-decisions":
        rows = decision_store.list_task_decisions(args.task_uid)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "show-runtime-events":
        rows = log_store.list_runtime_events(args.task_uid)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "refresh-affair-registry":
        payload = api.refresh_affair_registry(workspace_root=args.workspace_root, strict=bool(args.strict))
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "list-runtime-affairs":
        rows = api.list_runtime_affairs(workspace_root=args.workspace_root, strict=bool(args.strict))
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "check-affair-conflicts":
        payload = api.check_affair_conflicts(workspace_root=args.workspace_root)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "show-runtime-store-paths":
        payload = api.get_runtime_store_paths(base_dir=args.base_dir)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "show-affair-registry-paths":
        payload = api.get_affair_registry_paths(workspace_root=args.workspace_root)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    parser.print_help()
    return 1


def main() -> int:
    """CLI 主函数。"""

    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())

