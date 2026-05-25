# API手册

autodo-engine 的公开 API 位于 `autodoengine.api`，并由包入口 `autodoengine` 重新导出核心函数。当前 API 覆盖运行时初始化、任务推进、事务请求登记、决策部门治理、审计视图、事务注册与 capability 调用。

引擎支持两种运行模式：

- 独立模式：仅安装 autodo-engine，使用内置事务与内置工具。
- 增强模式：同时安装 autodo-kit，自动扩展官方事务与工具。

当前与 A055 预处理节点相关的边界约束：

1. AOE 负责固定主链与单节点主链执行，不负责承接 A055 四个 mode 配置的 direct-affair 语义。
2. `workspace/config/affairs_config/A055.json` 仍属于 AOE / PA 的正式单节点配置；其当前默认运行口径为 `local_dispatch_remote + remote_processing.enabled=true + use_tmux=false + allow_local_fallback=false`。
3. `A055.mode.local_only.minimal.json`、`A055.mode.local_dispatch_remote.minimal.json`、`A055.mode.remote_only_tmux.minimal.json`、`A055.mode.record_parse_results.minimal.json` 属于 AOK official affair 的直跑配置，并且都按单条 smoke 口径维护。
4. 如果调用方已经明确选择上述任一 mode 配置，则应绕过 AOE，直接调用 AOK 官方 `affair.execute(Path(config))`；AOE 不负责为这些 mode 配置补第二层单节点主链包装。
5. 只有当调用方显式要求“仍通过 PA 编排”时，才允许把这些 mode 配置重新包进 `run_project_mainflow(...)` 的单节点调用里。

## 1. 运行时与任务 API

### 1.1 load_graph(file_path)

从流程图 JSON 加载 `Graph` 对象。

### 1.2 bootstrap_runtime(base_dir)

初始化运行时目录与 SQLite 存储，包括 taskdb、logdb、decisiondb、graph_registry。

### 1.3 register_graph(graph)

注册流程图对象到 graph_registry。

### 1.4 create_task(title, goal_text, current_node_uid, parent_task_uid=None)

创建任务主记录。

### 1.5 run_task_step(task_uid, graph_uid)

执行单步任务推进，返回 `DecisionResult`。

### 1.6 run_task_until_wait(task_uid, graph_uid, max_steps=100)

持续执行直到等待态或终止态。

### 1.7 run_task_until_terminal(task_uid, graph_uid, max_steps=100)

持续执行直到 `completed`、`failed` 或 `cancelled`。

### 1.8 任务状态 / 动作 / 关系契约

核心枚举位于 `autodoengine.core.enums`。

`TaskStatus` 当前正式语义值：

1. `ready`
2. `running`
3. `suspended`
4. `blocked`
5. `completed`
6. `failed`
7. `cancelled`

`TaskAction` 当前正式语义值：

1. `continue`
2. `retry`
3. `backtrack`
4. `suspend`
5. `split`
6. `human_gate`
7. `complete`
8. `fail`
9. `cancel`

`RelationType` 当前正式语义值：

1. `split`
2. `depends_on`
3. `resume_from`

SQLite 物理层会把这些状态、动作、关系类型持久化为中文值；API 结果返回英文归一化语义字段，并在必要时补充中文字段。

## 2. 事务请求 API

### 2.1 create_task_request(request_type, target_affair_uid, payload=None, task_uid=None, source_object_type="", source_object_uid="", node_code="", config_path="", priority_score=0.0, source="任务系统", request_contract=None, metadata=None)

创建事务请求对象，并写入 `事务请求` 表。

返回对象包含：

1. `request_uid`
2. `task_uid`
3. `request_type`
4. `source_object_type`
5. `source_object_uid`
6. `node_code`
7. `target_affair_uid`
8. `config_path`
9. `request_contract`
10. `status`
11. `请求状态`
12. `priority_score`
13. `payload`
14. `metadata`
15. `created_at`
16. `updated_at`

这组桥接字段用于承接项目经理已经解析好的节点上下文，使项目仓库可以把 `node_inputs`、`node_contracts`、来源对象与 `config_path` 正式挂进 AOE 请求账本。

### 2.2 get_task_request(request_uid)

读取单个事务请求。

### 2.3 create_task_request_from_project_node(project_config_path, node_code, ...)

根据项目级 `config.json` 和节点编码自动构造标准事务请求。

该接口用于承接“项目经理先解配置、事务只消费配置”的编排模式，默认执行以下动作：

1. 读取项目级 `workspace_root`。
2. 从 `node_inputs[node_code]` 推断节点 `config_path`。
3. 从 `node_contracts[node_code]` 推断节点契约。
4. 从 `paths.affair_entry_registry_path` 推断 `target_affair_uid`。
5. 将这些项目事实写入标准请求对象的桥接字段。

### 2.4 list_task_requests(task_uid=None, status=None)

列出事务请求。

- 传入 `task_uid` 时，返回该任务下的请求列表。
- 不传 `task_uid` 时，返回全局请求列表，可选按 `status` 过滤。

### 2.4 当前调度边界

当前版本已经支持事务请求的正式登记、查询与状态回写，但尚未把事务请求自动纳入 `run_task_step(...)` / `run_task_until_wait(...)` / `run_task_until_terminal(...)` 的统一候选调度循环。

因此：

1. 事务请求已经是正式 SQLite 对象。
2. 调用方已经可以通过公开 API 和 CLI 对其进行读写，并写入项目级桥接字段。
3. “请求自动进入主循环统一排序并执行”仍属于后续阶段能力。

## 3. 决策部门治理 API

### 3.1 get_decision_department(department_uid="dept-default")

读取决策部门。

默认决策部门会自动确保存在，默认配置包括：

1. 默认部门 UID：`dept-default`
2. 默认 LLM 供应商：`阿里百炼`
3. 默认 LLM 模型：`qwen-max`
4. 默认决策模式：`联合决策`

### 3.2 list_decision_departments()

列出决策部门。

### 3.3 list_decision_department_members(department_uid="dept-default")

列出指定决策部门成员。

默认成员包括：

1. 人类成员
2. LLM 成员

### 3.4 当前治理边界

当前版本的决策部门对象首先承担治理配置与审计底座职责：

1. 它已经是正式 SQLite 对象。
2. 它已经能为“人类 + 阿里百炼 LLM”联合决策提供默认治理配置。
3. 调度器尚未在每一次任务决策时自动调用该部门配置去外发真实人类/LLM 决策请求。

## 4. 审计与路径 API

### 4.1 get_runtime_store_paths(base_dir=None)

返回运行时数据库目录与文件路径。

### 4.2 get_affair_registry_paths(workspace_root=None)

返回官方事务目录、官方事务数据库路径、用户事务目录与用户事务数据库路径。

### 4.3 get_task_full_chain_view(task_uid)

返回任务全链路审计视图。

### 4.4 get_decision_department_view(task_uid=None, decision_uid=None)

返回决策部门行为视图。

### 4.5 get_blocked_governance_view(task_uid=None)

返回阻断治理聚合视图。

## 5. 事务注册与直调 API

### 5.1 refresh_affair_registry(workspace_root=None, strict=False)

刷新官方事务库与用户事务库的运行时合并视图。

- 已安装 autodo-kit：官方事务来自 `autodokit/affairs`。
- 未安装 autodo-kit：自动回退到 `autodoengine/affairs`。

### 5.2 list_runtime_affairs(workspace_root=None, strict=False)

返回最终可见事务列表。

### 5.3 check_affair_conflicts(workspace_root=None)

返回事务冲突与告警信息。

### 5.4 prepare_affair_config(config, workspace_root)

将事务配置中的路径字段统一绝对化。

### 5.5 import_affair_module(affair_uid, workspace_root=None, strict=False)

按事务 UID 导入事务模块。优先使用 `runner.module`，若为空则回退到 `runner.source_py_path` 按源码文件路径加载。

### 5.6 import_user_affair(source_py_path, workspace_root, source_params_json_path=None, source_doc_md_path=None, affair_name=None, strict=False)

将用户功能程序导入为事务三件套目录（`affair.py`、`affair.json`、`affair.md`），并同步写入事务管理数据库。若名称冲突，自动按 `_v正整数` 追加后缀。

### 5.7 run_affair(...)

通过事务注册系统执行事务。

- 已安装 autodo-kit：可执行 kit 官方事务与用户事务。
- 未安装 autodo-kit：可执行 engine 内置事务与用户事务。

### 5.8 list_tools() / get_tool(tool_name)

按需桥接工具导出。

- 已安装 autodo-kit：优先桥接 `autodokit.tools`。
- 未安装 autodo-kit：回退到 `autodoengine.tools`。

## 6. Public Capability API

`autodoengine.tools.public` 提供统一的 manifest/schema/protocol/facade 能力面，并通过 `atomic -> public -> adapters` 三层结构对外暴露。

### 6.1 list_capabilities(include_internal=False)

列出 public capability 摘要清单。

### 6.2 lint_capabilities()

校验 capability manifest、schema 与实现可调用性。

### 6.3 invoke_capability(capability_id, payload=None, caller_context=None, allow_internal=False, workspace_root=None)

统一执行 capability，并返回标准协议结果：

1. `status`
2. `code`
3. `capability_id`
4. `data`
5. `audit_path`
6. `warnings`
7. `errors`
8. `metadata`

### 6.4 首批 capability 清单

| capability_id | exposure | side_effect | 说明 |
| --- | --- | --- | --- |
| runtime_show_paths | user | none | 查看运行时数据库目录与文件路径 |
| affair_show_paths | user | none | 查看事务管理系统路径 |
| affair_refresh | user | write | 刷新事务注册库并返回摘要 |
| affair_list | user | none | 列出运行时事务摘要列表 |
| affair_check_conflicts | user | none | 检查事务冲突与告警 |
| runtime_bootstrap | user | write | 初始化运行时目录结构 |
| graph_load_summary | user | none | 加载流程图并返回摘要 |
| affair_prepare_config | user | none | 预处理事务配置中的路径字段 |
| affair_run | developer | write | 执行事务并返回产物路径 |
| affair_import_user | developer | write | 导入用户功能程序为事务三件套 |

## 7. Skill 渲染 API

用于解析和参数化渲染规范的 `SKILL.md` 文件。

### 7.1 render_skill_prompt(skill_path, params, search_paths=None)

便捷函数：渲染 Skill 得到最终 Prompt 文本。

### 7.2 SkillRenderer

核心渲染逻辑封装，支持严格模式校验。

## 8. CLI 命令

当前 CLI 包含以下命令：

1. `init-runtime`
2. `register-graph`
3. `create-task`
4. `create-task-request`
5. `run-task-step`
6. `run-task`
7. `show-task`
8. `show-task-request`
9. `list-task-requests`
10. `show-decision-departments`
11. `show-decision-department-members`
12. `show-decisions`
13. `show-runtime-events`
14. `refresh-affair-registry`
15. `list-runtime-affairs`
16. `check-affair-conflicts`
17. `show-runtime-store-paths`
18. `show-affair-registry-paths`
19. `list-capabilities`
20. `invoke-capability`
21. `lint-capabilities`
