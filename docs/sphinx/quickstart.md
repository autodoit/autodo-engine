# 快速开始

## 安装文档依赖

```powershell
uv pip install --python .venv/Scripts/python.exe -r docs/sphinx/requirements.txt
```

## 安装引擎与事务库

```powershell
uv pip install -e .
uv pip install -e ../autodo-kit
```

## 初始化运行时

```powershell
python -m autodoengine.main init-runtime --base-dir ./.tmp/runtime_v4
```

## 构建 Sphinx HTML

```powershell
python -m sphinx -b html docs/sphinx docs/sphinx/_build/html
```
