# 图节点_start

## 用途

提供 autodo-engine 在未安装 autodo-kit 场景下的最小可运行 start 图节点事务。

## 输入

- `config_path`：JSON 配置文件路径。
- 支持字段：
  - `output_dir`：结果输出目录，未提供时默认写入配置文件同级目录。

## 输出

- 结果文件：`start_affair_result.json`。
- 返回结构遵循事务执行结果约定，`output_payload.artifacts` 包含结果文件绝对路径。
