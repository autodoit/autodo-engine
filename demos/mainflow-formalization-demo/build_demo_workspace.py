"""构造一个最小、干净、可 dry-run 的 ARK 风格主链工作区（引擎侧验证用）。

用途：在不改动 ARK 真仓、不删除任何东西的前提下，用 ARK 真实的 17 节点主链图与
在用的事务入口注册表（**只读取材**）新起一个干净工作区，灌入一个真实研究主题，
让 autodo-engine 自己解析/校验主链，验证「AOE 驱动 ARK 主链」这条路径是否真的通。

三份数据一律按宿主的**中文主契约**书写（config/注册表/流程图），以复现 ARK 的真实形态。

用法（引擎 venv，仓库根目录）：

```bash
.venv/bin/python demos/mainflow-formalization-demo/build_demo_workspace.py \
    --topic "数学形式化证明与自动化推导公式的研究"
```
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ARK_ROOT_DEFAULT = Path("/Users/ethan/CoreFiles/ProjectsFile/AcademicResearch-auto-workflow")
ARK_GRAPH_REL = Path(
    ".autodoengine/workflows/workflow_20260417_aoe_mainflow_v1/academic-research-mainflow-v3.0.0.json"
)
ARK_REGISTRY_REL = Path("workspace/config/affair_entry_registry.json")

DEMO_ROOT = Path(__file__).resolve().parent
WORKSPACE = DEMO_ROOT / "workspace"
CONFIG_DIR = WORKSPACE / "config"
AFFAIRS_CONFIG_DIR = CONFIG_DIR / "affairs_config"
GRAPH_DIR = DEMO_ROOT / ".autodoengine" / "workflows" / "aoe_mainflow_v1"

REQUIRED_ACTIONS = ["execute", "continue", "pause", "retry", "fallback", "stop", "gate_pass"]


def _node_uid_to_code(node_uid: str) -> str:
    normalized = str(node_uid or "").strip().lower()
    if normalized.startswith("n_"):
        normalized = normalized[2:]
    return normalized.upper()


def build(topic: str, ark_root: Path) -> Path:
    """生成干净工作区，返回 config.json 路径。"""

    graph_src = ark_root / ARK_GRAPH_REL
    registry_src = ark_root / ARK_REGISTRY_REL
    if not graph_src.exists() or not registry_src.exists():
        raise SystemExit(f"找不到 ARK 取材源：{graph_src} / {registry_src}")

    graph = json.loads(graph_src.read_text(encoding="utf-8"))
    registry = json.loads(registry_src.read_text(encoding="utf-8"))

    # 重建目录（仅限本 demo 目录内，绝不触碰 ARK）
    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT / "workspace", ignore_errors=True)
        shutil.rmtree(DEMO_ROOT / ".autodoengine", ignore_errors=True)
    AFFAIRS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    enabled_codes = [
        _node_uid_to_code(node["节点唯一标识"])
        for node in graph.get("节点", [])
        if node.get("是否启用", True)
    ]

    # 流程图：原样搬运（保持中文主契约），验证图侧归一化
    graph_out = GRAPH_DIR / "mainflow-v3.0.0.json"
    graph_out.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    # 注册表：结构原样，仅把路径改写指向本 demo 工作区
    records = []
    for record in registry.get("记录", []):
        code = str(record.get("节点编码") or "").strip().upper()
        if not code:
            continue
        rewritten = dict(record)
        rewritten["配置路径"] = str(AFFAIRS_CONFIG_DIR / f"{code}.json")
        records.append(rewritten)
    registry_out = {
        "契约版本": registry.get("契约版本", "demo"),
        "工作区根路径": str(WORKSPACE),
        "时区": "Asia/Shanghai",
        "记录": records,
    }
    registry_path = CONFIG_DIR / "affair_entry_registry.json"
    registry_path.write_text(json.dumps(registry_out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 每个节点一份最小入口配置；A030/A040 携带研究主题，证明主题真的进入链路
    for code in enabled_codes:
        payload: dict[str, object] = {"workspace_root": str(WORKSPACE)}
        if code in {"A030", "A040"}:
            payload["检索主题"] = topic
        (AFFAIRS_CONFIG_DIR / f"{code}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 项目 config：中文主契约（复现 ARK 真实书写方式）
    node_inputs = {code: f"config/affairs_config/{code}.json" for code in enabled_codes}
    project_config = {
        "工作流名称": "数学形式化证明主链验证",
        "工作区根路径": str(WORKSPACE),
        "项目": {"项目名称": "formalization-demo", "项目目标": topic},
        "运行时": {
            "流程图路径": str(graph_out.relative_to(DEMO_ROOT)),
            "开始节点": enabled_codes[0],
            "结束节点": enabled_codes[-1],
            "用户动作路由": {action: f"aoe.{action}" for action in REQUIRED_ACTIONS},
        },
        "路径": {"事务入口注册表路径": str(registry_path.relative_to(WORKSPACE))},
        "节点输入": node_inputs,
    }
    config_path = CONFIG_DIR / "config.json"
    config_path.write_text(json.dumps(project_config, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"工作区：{WORKSPACE}")
    print(f"启用节点 {len(enabled_codes)} 个：{' '.join(enabled_codes)}")
    return config_path


def main() -> None:
    parser = argparse.ArgumentParser(description="生成干净 ARK 风格主链工作区")
    parser.add_argument("--topic", default="数学形式化证明与自动化推导公式的研究")
    parser.add_argument("--ark-root", type=Path, default=ARK_ROOT_DEFAULT)
    args = parser.parse_args()
    build(topic=args.topic, ark_root=args.ark_root)


if __name__ == "__main__":
    main()
