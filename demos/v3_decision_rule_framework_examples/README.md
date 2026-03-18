# v3 决策规则框架示例

本目录提供一套“可读 + 可跑”的最小示例：

- `aof.md`：使用 AOF/Mermaid 风格表达流程图结构。
- `workflow_pa_only.json`：仅 PA 介入模板。
- `workflow_human_only.json`：仅人工介入模板。
- `workflow_pa_human.json`：PA + 人工联合介入模板。

说明：

- 当前示例应通过 `autodoengine.api.load_graph()` 或 `python -m autodoengine.main ...` 运行。
- `aof.md` 作为结构源表达，帮助后续统一迁移到 AOF 驱动的流程图定义方式。

推荐运行方式：

```powershell
C:/Users/Ethan/CoreFiles/ProjectsFile/autodo-kit/.venv/Scripts/python.exe demos/scripts/demo_v3_decision_rule_framework_examples.py
```

脚本会分别运行三套模板，并把结果写到：

- `demos/output/runtime_v3_decision_rule_framework_examples/`
