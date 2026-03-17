# autodo-engine

autodo-engine 是 AOK 的流程引擎仓，负责流程图加载、任务调度、决策闭环、审计视图与事务注册运行时。

官方事务内容已拆分到 autodo-kit。本仓库保留的是引擎能力，不再内置 affairs 目录。

## 安装关系

```powershell
uv pip install -e .
uv pip install -e ../autodo-kit
```

建议同时安装 autodo-kit，以便：

- 通过事务注册系统发现官方事务
- 使用 run_affair 直调官方事务
- 让节点模板从官方 affair.json 生成

## 核心目录

```text
autodoengine/
  core/         协议与错误定义
  flow_graph/   流程图模型、校验、模板装载
  scheduling/   单步闭环、候选动作、决策规则
  taskdb/       运行时数据库与审计视图
  utils/        配置、路径、事务注册、公共辅助
  api.py        对外 Python API
  main.py       CLI 入口
```

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
