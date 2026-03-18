# v3 决策规则框架示例 AOF

下面的 AOF 只表达结构骨架，不直接承载运行时全部策略字段。当前仓库的公开稳定运行口径仍以旁边三份 `workflow_*.json` 为准。

## 1. 基础流程图

```aof
flowchart TD
    node-start<start>[affair:affair-start]
    node-decision<process>[affair:affair-decision]
    node-end<end>[affair:affair-end]

    node-start --> node-decision
    node-decision --> node-end
```

## 2. 结构含义

- `node-start`：起点，默认直流。
- `node-decision`：决策节点，用于演示 `route_mode=decision` 与 `decision_rule_framework`。
- `node-end`：终点，命中 `goal_satisfied_at_node=true` 后可完成任务。

## 3. 三种模板如何映射到 workflow.json

### 3.1 PA only

- `graph.policies.decision_rule_framework.intervention_condition = abnormal_upgrade`
- `graph.policies.decision_rule_framework.intervention_actors = ["pa"]`
- `node-decision.policies.route_mode = decision`
- `node-decision.policies.simulate_receipt.result_code = BLOCKED`

### 3.2 human only

- `graph.policies.decision_rule_framework.intervention_condition = abnormal_upgrade`
- `graph.policies.decision_rule_framework.intervention_actors = ["pa"]`
- `node-decision.policies.route_mode = decision`
- `node-decision.policies.decision_rule_framework.intervention_condition = always`
- `node-decision.policies.decision_rule_framework.intervention_actors = ["human"]`

### 3.3 PA + human

- `node-decision.policies.route_mode = decision`
- `node-decision.policies.decision_rule_framework.intervention_condition = always`
- `node-decision.policies.decision_rule_framework.intervention_actors = ["pa", "human"]`
