"""v3 决策规则框架示例批量演练脚本。"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import autodokit as aok
from autodokit.taskdb import decision_store, log_store, task_store


def _demo_root() -> Path:
    """返回 demos 根目录。

    Returns:
        Path: demos 根目录绝对路径。

    Examples:
        >>> _demo_root().name
        'demos'
    """

    return Path(__file__).resolve().parents[1]


def _workflow_dir() -> Path:
    """返回决策规则框架示例目录。

    Returns:
        Path: workflow 示例目录。

    Examples:
        >>> _workflow_dir().name
        'v3_decision_rule_framework_examples'
    """

    return _demo_root() / "workflows" / "v3_decision_rule_framework_examples"


def _runtime_root(example_name: str) -> Path:
    """返回单个示例的运行时目录。

    Args:
        example_name: 示例名称。

    Returns:
        Path: 运行时目录。

    Examples:
        >>> _runtime_root("pa_only").name
        'pa_only'
    """

    return _demo_root() / "output" / "runtime_v3_decision_rule_framework_examples" / example_name


def _workflow_files() -> dict[str, Path]:
    """返回全部示例文件映射。

    Returns:
        dict[str, Path]: 示例名到 workflow 文件的映射。

    Examples:
        >>> sorted(_workflow_files().keys())
        ['human_only', 'pa_human', 'pa_only']
    """

    workflow_dir = _workflow_dir()
    return {
        "pa_only": workflow_dir / "workflow_pa_only.json",
        "human_only": workflow_dir / "workflow_human_only.json",
        "pa_human": workflow_dir / "workflow_pa_human.json",
    }


def run_example(example_name: str, workflow_file: Path) -> dict[str, object]:
    """运行单个决策规则框架示例。

    Args:
        example_name: 示例名称。
        workflow_file: workflow JSON 文件路径。

    Returns:
        dict[str, object]: 演练结果摘要。

    Raises:
        FileNotFoundError: 当 workflow 文件不存在时抛出。

    Examples:
        >>> files = _workflow_files()
        >>> isinstance(files["pa_only"], Path)
        True
    """

    if not workflow_file.exists():
        raise FileNotFoundError(f"workflow 文件不存在：{workflow_file}")

    runtime_root = _runtime_root(example_name)
    aok.bootstrap_runtime(str(runtime_root))
    graph = aok.load_graph(str(workflow_file))
    aok.register_graph(graph)

    task = aok.create_task(
        title=f"决策规则框架示例-{example_name}",
        goal_text=f"验证 {example_name} 模板行为",
        current_node_uid="node-start",
    )
    task_uid = str(task["task_uid"])

    task_store.update_task_metadata(
        task_uid,
        {
            "workspace_root": str(_demo_root()),
            "demo_name": example_name,
        },
    )

    decisions = aok.run_task_until_wait(task_uid=task_uid, graph_uid=graph.graph_uid, max_steps=10)
    final_task = task_store.get_task(task_uid)
    decision_rows = decision_store.list_task_decisions(task_uid)
    event_rows = log_store.list_runtime_events(task_uid)

    summary = {
        "example_name": example_name,
        "workflow_file": str(workflow_file),
        "runtime_root": str(runtime_root),
        "graph_uid": graph.graph_uid,
        "task_uid": task_uid,
        "final_status": final_task.get("status"),
        "decision_count": len(decisions),
        "decisions": [asdict(item) for item in decisions],
        "decision_rows": decision_rows,
        "event_count": len(event_rows),
        "events": event_rows,
    }

    report_path = runtime_root / f"{example_name}_report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary["report_path"] = str(report_path)
    return summary


def run_all_examples() -> dict[str, object]:
    """批量运行全部决策规则框架示例。

    Returns:
        dict[str, object]: 全部示例摘要。

    Examples:
        >>> isinstance(_workflow_files(), dict)
        True
    """

    outputs: dict[str, object] = {}
    for example_name, workflow_file in _workflow_files().items():
        outputs[example_name] = run_example(example_name, workflow_file)

    report_path = _demo_root() / "output" / "runtime_v3_decision_rule_framework_examples" / "summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(outputs, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {
        "examples": outputs,
        "summary_report": str(report_path),
    }


def main() -> None:
    """脚本入口。"""

    result = run_all_examples()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()