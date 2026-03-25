# 引擎运行时探针

## 用途

通过 capability facade 串联 `runtime_bootstrap` 与 `runtime_show_paths`，验证运行时目录初始化和路径查询的一致性。

## 输入

- `runtime_base_dir`：运行时根目录。
- `output_dir`：结果输出目录。

## 输出

- `engine_runtime_probe_result.json`
