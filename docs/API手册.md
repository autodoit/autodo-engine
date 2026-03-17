# API手册

autodo-engine 的公开 API 位于 autodoengine.api，面向运行时初始化、流程图执行、审计查询与事务直调。

## 1. 运行时 API

### 1.1 load_graph(file_path)

从流程图 JSON 加载 Graph 对象。

### 1.2 bootstrap_runtime(base_dir)

初始化 taskdb、logdb、decisiondb、graph_registry 目录。

### 1.3 register_graph(graph)

注册流程图对象到 graph_registry。

### 1.4 create_task(title, goal_text, current_node_uid, parent_task_uid=None)

创建任务主记录。

### 1.5 run_task_step(task_uid, graph_uid)

执行单步任务推进，返回 DecisionResult。

### 1.6 run_task_until_wait(task_uid, graph_uid, max_steps=100)

持续执行直到等待态或终止态。

### 1.7 run_task_until_terminal(task_uid, graph_uid, max_steps=100)

持续执行直到 completed、failed 或 cancelled。

## 2. 审计与路径 API

### 2.1 get_runtime_store_paths(base_dir=None)

返回运行时数据库目录与文件路径。

### 2.2 get_affair_registry_paths(workspace_root=None)

返回官方事务目录、官方事务数据库路径、用户事务目录与用户事务数据库路径。

### 2.3 get_task_full_chain_view(task_uid)

返回任务全链路审计视图。

### 2.4 get_decision_department_view(task_uid=None, decision_uid=None)

返回决策部门行为视图。

### 2.5 get_blocked_governance_view(task_uid=None)

返回阻断治理聚合视图。

## 3. 事务注册与直调 API

### 3.1 refresh_affair_registry(workspace_root=None, strict=False)

刷新官方事务库与用户事务库的运行时合并视图。官方事务内容来自 autodo-kit。

### 3.2 list_runtime_affairs(workspace_root=None, strict=False)

返回最终可见事务列表。

### 3.3 check_affair_conflicts(workspace_root=None)

返回事务冲突与告警信息。

### 3.4 prepare_affair_config(config, workspace_root)

将事务配置中的路径字段统一绝对化。

### 3.5 import_affair_module(affair_uid, workspace_root=None, strict=False)

按事务 UID 解析 runner.module 并导入模块。

### 3.6 run_affair(...)

通过事务注册系统执行事务。若未安装 autodo-kit，则无法定位官方事务。

### 3.7 list_tools() / get_tool(tool_name)

按需桥接 autodokit.tools 的导出工具；本仓不再自带 tools 包。

## 4. CLI 命令

- init-runtime
- register-graph
- create-task
- run-task-step
- run-task
- show-task
- show-decisions
- show-runtime-events
- refresh-affair-registry
- list-runtime-affairs
- check-affair-conflicts
- show-runtime-store-paths
- show-affair-registry-paths
