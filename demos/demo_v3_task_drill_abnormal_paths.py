"""v3 异常路径专项演练脚本。"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

import autodokit as aok
from autodokit.taskdb import decision_store, list_graphs, log_store, relation_store, snapshot_store, step_store, task_store


def _demo_root() -> Path:
    """返回 demos 根目录。"""

    return Path(r"C:\Users\Ethan\CoreFiles\ProjectsFile\autodo-kit\demos").resolve()


def _runtime_root() -> Path:
    """返回异常路径演练根目录。"""

    return (_demo_root() / "output" / "runtime_v3_task_drill_abnormal_paths").resolve()


def _prepare_runtime(case_name: str) -> Path:
    """准备单组运行时目录。"""

    runtime = (_runtime_root() / case_name).resolve()
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


def _write_graph(runtime: Path, graph_payload: dict[str, Any]) -> Path:
    """将图写入运行时目录。"""

    graph_file = runtime / "graph.json"
    graph_file.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph_file


def _health_summary(task_uid: str, graph_uid: str) -> dict[str, Any]:
    """汇总数据库健康信息。"""

    return {
        "task": task_store.get_task(task_uid),
        "decisions": decision_store.list_task_decisions(task_uid),
        "events": log_store.list_runtime_events(task_uid),
        "steps": [asdict(item) for item in step_store.list_task_steps(task_uid)],
        "snapshots": snapshot_store.list_task_snapshots(task_uid),
        "relations": relation_store.list_children(task_uid),
        "graphs": list_graphs(),
        "graph_uid": graph_uid,
    }


def _run_retry_case() -> dict[str, Any]:
    """运行 RETRY 路径演练。"""

    runtime = _prepare_runtime("retry")
    graph_payload = {
        "graph_uid": "graph-retry-demo",
        "graph_name": "RETRY 演练图",
        "graph_version": "0.1.0",
        "nodes": [
            {
                "node_uid": "node-retry",
                "node_type": "process",
                "affair_uid": "affair-retry",
                "policies": {
                    "simulate_receipt": {
                        "result_code": "RETRY",
                        "retryable": True,
                        "requires_human": False,
                        "message": "依赖暂未就绪，建议重试",
                    }
                },
                "enabled": True,
            }
        ],
        "edges": [],
    }

    aok.bootstrap_runtime(str(runtime))
    graph = aok.load_graph(str(_write_graph(runtime, graph_payload)))
    aok.register_graph(graph)
    task = aok.create_task(title="RETRY 演练", goal_text="验证 retry 路径", current_node_uid="node-retry")
    decision = aok.run_task_step(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid)
    health = _health_summary(str(task["task_uid"]), graph.graph_uid)
    return {
        "case_name": "retry",
        "runtime_root": str(runtime),
        "decision": asdict(decision),
        "retry_count": health["task"].get("retry_count"),
        "final_status": health["task"].get("status"),
        "health": health,
    }


def _run_blocked_case() -> dict[str, Any]:
    """运行 BLOCKED + human_gate 路径演练。"""

    runtime = _prepare_runtime("blocked")
    graph_payload = {
        "graph_uid": "graph-blocked-demo",
        "graph_name": "BLOCKED 演练图",
        "graph_version": "0.1.0",
        "nodes": [
            {
                "node_uid": "node-blocked",
                "node_type": "process",
                "affair_uid": "affair-blocked",
                "policies": {
                    "simulate_receipt": {
                        "result_code": "BLOCKED",
                        "block_reason_code": "permission_missing",
                        "block_scope": "node",
                        "requires_human": True,
                        "retryable": False,
                        "message": "权限不足，需要人工确认",
                    }
                },
                "enabled": True,
            }
        ],
        "edges": [],
    }

    aok.bootstrap_runtime(str(runtime))
    graph = aok.load_graph(str(_write_graph(runtime, graph_payload)))
    aok.register_graph(graph)
    task = aok.create_task(title="BLOCKED 演练", goal_text="验证 blocked 路径", current_node_uid="node-blocked")
    decisions = aok.run_task_until_wait(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid, max_steps=3)
    health = _health_summary(str(task["task_uid"]), graph.graph_uid)
    blocked_events = [item for item in health["events"] if item.get("event_type") == "human_gate_requested"]
    return {
        "case_name": "blocked",
        "runtime_root": str(runtime),
        "decisions": [asdict(item) for item in decisions],
        "final_status": health["task"].get("status"),
        "human_gate_pending": bool((health["task"].get("metadata") or {}).get("human_gate_pending", False)),
        "blocked_event_count": len(blocked_events),
        "snapshot_count": len(health["snapshots"]),
        "health": health,
    }


def _run_split_case() -> dict[str, Any]:
    """运行 split 路径演练。"""

    runtime = _prepare_runtime("split")
    graph_payload = {
        "graph_uid": "graph-split-demo",
        "graph_name": "split 演练图",
        "graph_version": "0.1.0",
        "nodes": [
            {
                "node_uid": "node-split",
                "node_type": "process",
                "affair_uid": "affair-split",
                "policies": {
                    "force_split_hint": True,
                    "simulate_receipt": {
                        "result_code": "BLOCKED",
                        "block_reason_code": "goal_ambiguous",
                        "block_scope": "task",
                        "requires_human": False,
                        "retryable": False,
                        "message": "目标不明确，需要拆分",
                    },
                },
                "enabled": True,
            }
        ],
        "edges": [],
    }

    aok.bootstrap_runtime(str(runtime))
    graph = aok.load_graph(str(_write_graph(runtime, graph_payload)))
    aok.register_graph(graph)
    task = aok.create_task(title="split 演练", goal_text="验证 split 路径", current_node_uid="node-split")
    decision = aok.run_task_step(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid)
    health = _health_summary(str(task["task_uid"]), graph.graph_uid)
    return {
        "case_name": "split",
        "runtime_root": str(runtime),
        "decision": asdict(decision),
        "final_status": health["task"].get("status"),
        "child_count": len(health["relations"]),
        "health": health,
    }


def _run_resume_case() -> dict[str, Any]:
    """运行 resume 路径演练。"""

    runtime = _prepare_runtime("resume")
    graph_payload = {
        "graph_uid": "graph-resume-demo",
        "graph_name": "resume 演练图",
        "graph_version": "0.1.0",
        "nodes": [
            {
                "node_uid": "node-split",
                "node_type": "process",
                "affair_uid": "affair-split",
                "policies": {
                    "force_split_hint": True,
                    "simulate_receipt": {
                        "result_code": "BLOCKED",
                        "block_reason_code": "goal_ambiguous",
                        "block_scope": "task",
                        "requires_human": False,
                        "retryable": False,
                        "message": "目标不明确，需要拆分",
                    },
                },
                "enabled": True,
            }
        ],
        "edges": [],
    }

    aok.bootstrap_runtime(str(runtime))
    graph = aok.load_graph(str(_write_graph(runtime, graph_payload)))
    aok.register_graph(graph)
    task = aok.create_task(title="resume 演练", goal_text="验证 resume 路径", current_node_uid="node-split")
    first = aok.run_task_step(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid)
    relations = relation_store.list_children(str(task["task_uid"]))
    for relation in relations:
        task_store.mark_task_completed(str(relation["child_task_uid"]))
    second = aok.run_task_step(task_uid=str(task["task_uid"]), graph_uid=graph.graph_uid)
    health = _health_summary(str(task["task_uid"]), graph.graph_uid)
    return {
        "case_name": "resume",
        "runtime_root": str(runtime),
        "first_decision": asdict(first),
        "second_decision": asdict(second),
        "final_status": health["task"].get("status"),
        "resume_candidates": relation_store.find_resume_candidates(str(task["task_uid"])),
        "health": health,
    }


def _render_report(report: dict[str, Any]) -> str:
    """渲染 Markdown 报告。"""

    lines = [
        "# v3 异常路径专项演练报告",
        "",
        "## 1. 覆盖路径",
        "",
        "- RETRY",
        "- BLOCKED + human_gate",
        "- split -> suspended",
        "- child completed -> resume -> ready",
        "",
        "## 2. 结论摘要",
        "",
    ]

    for case_name in ["retry", "blocked", "split", "resume"]:
        case = report[case_name]
        lines.append(f"### {case_name}")
        lines.append("")
        lines.append(f"- 最终状态：`{case['final_status']}`")
        if case_name == "retry":
            lines.append(f"- retry_count：`{case['retry_count']}`")
        if case_name == "blocked":
            lines.append(f"- human_gate_pending：`{case['human_gate_pending']}`")
            lines.append(f"- blocked_event_count：`{case['blocked_event_count']}`")
            lines.append(f"- snapshot_count：`{case['snapshot_count']}`")
        if case_name == "split":
            lines.append(f"- child_count：`{case['child_count']}`")
        if case_name == "resume":
            lines.append(f"- resume_candidates：`{len(case['resume_candidates'])}`")
        lines.append("")

    return "\n".join(lines) + "\n"


def run_abnormal_drill() -> dict[str, Any]:
    """执行异常路径专项演练。"""

    retry = _run_retry_case()
    blocked = _run_blocked_case()
    split = _run_split_case()
    resume = _run_resume_case()

    root = _runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    report = {
        "report_name": "v3_abnormal_paths_drill",
        "retry": retry,
        "blocked": blocked,
        "split": split,
        "resume": resume,
        "json_report_path": str((root / "abnormal_paths_report.json").resolve()),
        "md_report_path": str((root / "abnormal_paths_report.md").resolve()),
    }
    Path(report["json_report_path"]).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    Path(report["md_report_path"]).write_text(_render_report(report), encoding="utf-8")
    return report


def main() -> None:
    """脚本入口。"""

    report = run_abnormal_drill()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()