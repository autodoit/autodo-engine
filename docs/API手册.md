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

按事务 UID 导入事务模块。优先使用 `runner.module`，若为空则回退到 `runner.source_py_path` 按源码文件路径加载。

### 3.6 import_user_affair(source_py_path, workspace_root, source_params_json_path=None, source_doc_md_path=None, affair_name=None, strict=False)

将用户功能程序导入为事务三件套目录（`affair.py`、`affair.json`、`affair.md`），并同步写入事务管理数据库。若名称冲突，自动按 `_v正整数` 追加后缀。

### 3.7 run_affair(...)

通过事务注册系统执行事务。若未安装 autodo-kit，则无法定位官方事务。

### 3.8 list_tools() / get_tool(tool_name)

按需桥接 autodokit.tools 的导出工具；本仓不再自带 tools 包。

## 4. Skill 渲染 API

用于解析和参数化渲染规范的 `SKILL.md` 文件。

### 4.1 render_skill_prompt(skill_path, params, search_paths=None)

便捷函数：渲染 Skill 得到最终 Prompt 文本。

- **Args**:
  - `skill_path`: `SKILL.md` 文件的绝对路径。
  - `params`: 参数字典，键需匹配 `SKILL.md` 中的 Jinja2 变量。
  - `search_paths`: 可选的模板搜索路径列表（支持 `include`/`import` 逻辑）。
- **Returns**: 渲染后的 Prompt 字符串。

### 4.2 SkillRenderer 类

核心渲染逻辑封装，支持严格模式校验。

- **Methods**:
  - `load_skill(skill_path)`: 加载元数据与模板正文。
  - `validate_params(meta, params)`: 返回缺失的可选或必需参数列表。
  - `render(skill_path, params)`: 执行完整渲染。

## 5. CLI 命令

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
