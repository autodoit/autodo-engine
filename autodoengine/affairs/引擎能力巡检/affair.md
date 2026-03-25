# 引擎能力巡检

## 用途

通过 capability facade 连续调用 `affair_refresh` 与 `affair_show_paths`，验证引擎工具平台最小闭环。

## 输入

- `output_dir`：结果输出目录。
- `strict`：事务刷新是否使用严格模式。

## 输出

- `engine_capability_inspection_result.json`
