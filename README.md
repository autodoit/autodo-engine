# autodo-engine

autodo-engine 是 AOK 的流程引擎仓，负责流程图加载、任务调度、决策闭环、审计视图与事务注册运行时。

本仓库可独立运行，内置最小事务与最小工具集；`autodo-kit` 作为可选增强包提供更完整的事务与工具内容。

AOE 主链的 workflow 资产与 runtime 留痕统一放在 `workflows/workflow_20260417_aoe_mainflow_v1/`。

## 安装关系

仅安装 engine（独立模式）：

```powershell
uv pip install -e .
```

可选安装 autodo-kit（增强模式）：

```powershell
uv pip install -e ../autodo-kit
```

安装 autodo-kit 后可获得：

- 通过事务注册系统发现官方事务
- 使用 run_affair 直调官方事务
- 让节点模板从官方 affair.json 生成

未安装 autodo-kit 时，engine 将自动回退到内置事务目录 `autodoengine/affairs` 与内置工具模块 `autodoengine.tools`。

## 核心目录

```text
autodoengine/
  core/         协议与错误定义
  flow_graph/   流程图模型、校验、模板装载
  scheduling/   单步闭环、候选动作、决策规则
  taskdb/       运行时数据库与审计视图
  utils/        配置、路径、事务注册、公共辅助
  tools/        atomic/public/adapters 工具平台
  api.py        对外 Python API
  main.py       CLI 入口
```

## 工具平台

`autodo-engine` 现已内置一套可独立运行的工具平台，结构如下：

```text
autodoengine/tools/
  atomic/      原子能力实现
  public/      manifest/schema/protocol/facade
  adapters/    cli/python/agent/runner 多入口适配
```

首批 capability 包含：

- `runtime_show_paths`
- `affair_show_paths`
- `affair_refresh`
- `affair_list`
- `affair_check_conflicts`
- `runtime_bootstrap`
- `graph_load_summary`
- `affair_prepare_config`
- `affair_run`
- `affair_import_user`

## 常用操作

初始化运行时：

```powershell
python -m autodoengine.main init-runtime --base-dir ./.tmp/runtime
```

执行流程：

```powershell
python -m autodoengine.main run-task --task-uid <task_uid> --graph-uid <graph_uid> --max-steps 50
```

直调事务：

```python
from pathlib import Path
from autodoengine import api

outputs = api.run_affair(
    "图节点_start",
    config={"output_dir": "output/demo"},
    workspace_root=Path.cwd(),
)
print(outputs)
```

独立模式最小事务检查：

```powershell
python -m autodoengine.main refresh-affair-registry
python -m autodoengine.main list-runtime-affairs
```

统一 capability 调用：

```powershell
python -m autodoengine.main list-capabilities
python -m autodoengine.main invoke-capability --capability-id affair_refresh --payload-json '{"workspace_root":"."}'
python -m autodoengine.main lint-capabilities
```

Python import 调用：

```python
from pathlib import Path
from autodoengine import api

result = api.invoke_capability(
  "affair_show_paths",
  payload={"workspace_root": str(Path.cwd())},
  workspace_root=Path.cwd(),
)
print(result)
```

Runner 参数文件调用：

```powershell
python scripts/invoke_capability.py path/to/params.json
```
