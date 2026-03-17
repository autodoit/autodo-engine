"""配置与密钥加载工具。

本模块用于集中处理两类配置：
1) 调度配置：`settings/配置文件/config.json`。
2) 密钥配置：在 `config.json` 中通过路径指向一个 `.env` 文件（支持绝对/相对路径）。

设计目标：
- 让“配置文件路径规则”集中在一个位置维护，避免散落在各脚本里。
- 支持将密钥文件放在 iCloud / OneDrive 等同步目录中，通过绝对路径引用。
- 不在仓库中硬编码任何 API Key；环境变量始终具有最高优先级。

注意：
- 该模块只实现最小 `.env` 解析（KEY=VALUE、注释、空行），避免引入额外依赖。
- 全局调度配置 `config.json` 支持外置：可通过函数参数或环境变量 `AOK_CONFIG` 指定任意路径。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List

from autodoengine.utils.path_tools import find_repo_root, load_json_or_py, resolve_path_from_base


@dataclass(frozen=True)
class AppConfig:
    """工具包运行配置。

    Args:
        workspace_root: 工作区根目录（可相对/绝对）。
        run: 需要运行的 workflow 配置列表（可写相对 `workspace_root` 的路径或绝对路径）。
        skip: 需要跳过的项目列表。
        secrets_file: 指向密钥 `.env` 文件的路径（可相对/绝对）。
    """

    workspace_root: Optional[str] = None  # 工作区根目录（公开主契约）
    run: list[str] = None  # type: ignore[assignment]
    skip: list[str] = None  # type: ignore[assignment]
    secrets_file: Optional[str] = None  # 密钥文件路径（可选）


def _repo_root_from_config_path(config_path: Path) -> Path:
    """从配置文件路径推断仓库根目录。"""

    return find_repo_root(config_path)


def _expand_path(raw: str, *, base_dir: Path) -> Path:
    """展开环境变量与 `~`，并将相对路径基于 base_dir 解析。"""

    return resolve_path_from_base(raw, base_dir=base_dir)


# 说明：仓库当前默认调度配置位于 config/config.json。
# 同时保留对旧路径 settings/配置文件/config.json 的兼容，方便历史项目不改路径继续运行。
DEFAULT_CONFIG_RELATIVE_PATH = Path("config/config.json")
_OLD_DEFAULT_CONFIG_RELATIVE_PATH = Path("settings/配置文件/config.json")


def resolve_config_path(
    config_path: str | Path | None = None,
    *,
    env_var_name: str = "AOK_CONFIG",
    default_relative_path: str | Path = DEFAULT_CONFIG_RELATIVE_PATH,
    cwd: str | Path | None = None,
) -> Path:
    """解析全局调度配置 `config.json` 的实际路径。

    设计原因：
    - 工具包以 editable 方式安装到第三方项目后，配置文件不应再固定在包内。
    - 通过“显式参数 / 环境变量 / 默认相对路径”三种方式，让 CLI、PyCharm 运行、第三方脚本调用都能稳定定位配置。

    优先级：
    1) 显式参数 config_path
    2) 环境变量 env_var_name（默认 `AOK_CONFIG`）
    3) default_relative_path（默认 `config/config.json`，相对 cwd 解析）

    Args:
        config_path: 显式指定的配置文件路径（可相对/绝对）。
        env_var_name: 环境变量名，用于指定外置配置文件路径。
        default_relative_path: 未指定时使用的默认相对路径。
        cwd: 解析相对路径时使用的工作目录；不提供则使用当前进程的 cwd。

    Returns:
        解析后的配置文件绝对路径。

    Raises:
        FileNotFoundError: 解析出的配置文件路径不存在。
    """

    base = Path(cwd) if cwd is not None else Path.cwd()

    raw: str | Path | None = None
    if config_path is not None and str(config_path).strip():
        raw = config_path
    else:
        env_v = (os.getenv(env_var_name) or "").strip()
        if env_v:
            raw = env_v
        else:
            # 兼容：如果新默认路径不存在但旧路径存在，则自动回退。
            cand_new = Path(default_relative_path)
            cand_old = _OLD_DEFAULT_CONFIG_RELATIVE_PATH
            if not (base / cand_new).exists() and (base / cand_old).exists():
                raw = cand_old
            else:
                raw = default_relative_path

    p = Path(raw)
    if not p.is_absolute():
        p = (base / p).resolve()
    else:
        p = p.resolve()

    if not p.exists():
        raise FileNotFoundError(
            f"找不到配置文件：{p}。你可以通过参数 config_path 或环境变量 {env_var_name} 指定外置 config.json。"
        )

    return p


def load_config(config_path: str | Path = DEFAULT_CONFIG_RELATIVE_PATH) -> AppConfig:
    """加载调度配置文件。"""

    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"找不到配置文件：{p}")

    try:
        data = load_json_or_py(p)
    except ValueError as exc:
        raise ValueError(f"配置文件不是合法 JSON：{p}：{exc}") from exc

    workspace_root = data.get("workspace_root")
    run = data.get("run")
    skip = data.get("skip") or []

    if workspace_root is not None and not isinstance(workspace_root, str):
        raise ValueError("config.json 的 workspace_root 字段必须是字符串或不提供")
    if run is None:
        raise ValueError(
            "config.json 缺少 run 字段。示例：\n"
            '{"workspace_root":"...", "run": ["workflows/workflow_010/workflow.json"], "skip": []}\n'
        )
    if not isinstance(run, list):
        raise ValueError("config.json 的 run 字段必须是列表")
    if not isinstance(skip, list):
        raise ValueError("config.json 的 skip 字段必须是列表")

    secrets_file = data.get("secrets_file")
    if secrets_file is not None and not isinstance(secrets_file, str):
        raise ValueError("config.json 的 secrets_file 字段必须是字符串或不提供")

    return AppConfig(
        workspace_root=workspace_root.strip() if isinstance(workspace_root, str) and workspace_root.strip() else None,
        run=[str(x) for x in run],
        skip=[str(x) for x in skip],
        secrets_file=secrets_file,
    )


def resolve_secrets_file_path(
    config_path: str | Path = DEFAULT_CONFIG_RELATIVE_PATH,
) -> Optional[Path]:
    """解析密钥文件路径（可相对/绝对）。

    Args:
        config_path: 配置文件路径。

    Returns:
        密钥文件 Path；若未配置则返回 None。

    Raises:
        FileNotFoundError: 配置了 secrets_file 但文件不存在。
    """

    cfg = load_config(config_path)
    if not cfg.secrets_file:
        return None

    base_dir = _repo_root_from_config_path(Path(config_path))
    secrets_path = _expand_path(cfg.secrets_file, base_dir=base_dir).resolve()

    if not secrets_path.exists():
        raise FileNotFoundError(f"密钥文件不存在：{secrets_path}")
    if not secrets_path.is_file():
        raise FileNotFoundError(f"密钥路径不是文件：{secrets_path}")
    return secrets_path


def _strip_wrapping_quotes(value: str) -> str:
    """去除值两端的包裹引号。

    为什么需要这个函数：
    - 许多用户会在 .env 或 txt 中写 `KEY="value"`。
    - 本项目的轻量解析器默认不做复杂语法解析，但至少应兼容最常见的引号写法，
      避免把引号本身当作密钥的一部分导致鉴权失败。

    Args:
        value: 原始值字符串。

    Returns:
        去除包裹引号后的值。
    """

    v = (value or "").strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1].strip()
    return v


def _parse_dotenv_file(dotenv_path: Path) -> Dict[str, str]:
    """解析极简 `.env` 文件。

    仅支持：
    - 空行
    - 以 # 开头的注释行
    - KEY=VALUE 键值对

    兼容增强：
    - 允许行首出现 `export `（常见于 bash/zsh）
    - 允许值被单引号/双引号包裹，例如 `KEY="value"`
    - 允许文件为纯 key 文件（只有一行 key），此时会映射到 `DASHSCOPE_API_KEY`

    Args:
        dotenv_path: `.env` 文件路径。

    Returns:
        解析出的键值对字典。
    """

    result: Dict[str, str] = {}

    # 关键：处理 UTF-8 BOM，避免第一行 key 变成 '\ufeffDASHSCOPE_API_KEY'
    text = dotenv_path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    # 兼容：如果是“纯 key 文件”，直接按默认变量名注入。
    # 为什么这样做：有些用户会把 secrets_file 指到一个 txt，只写 sk-xxx。
    # 这样可以在不引入额外依赖的前提下提升易用性。
    non_empty_non_comment = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if non_empty_non_comment and all("=" not in ln for ln in non_empty_non_comment):
        if len(non_empty_non_comment) == 1:
            result["DASHSCOPE_API_KEY"] = _strip_wrapping_quotes(non_empty_non_comment[0])
            return result

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # 兼容 bash 的 export 前缀
        if line.lower().startswith("export "):
            line = line[7:].lstrip()

        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if not k:
            continue
        result[k] = _strip_wrapping_quotes(v)

    return result


def _parse_api_keys_text(text: str, *, key_name: str = "DASHSCOPE_API_KEY") -> List[str]:
    """从文本中解析多个 API Key。

    支持格式（可混用）：
    1) 一行一个 key：
       sk-xxx
       sk-yyy
    2) KEY=VALUE：
       DASHSCOPE_API_KEY=sk-xxx
       DASHSCOPE_API_KEY=sk-yyy
       default=sk-zzz
    3) 允许注释与空行：以 # 开头的行会被跳过。

    设计原因：
    - 你希望未来在一个 txt 文件里写入多个 keys，并按规则选择。
    - 这里保持解析器足够“宽容”，避免因为格式差异导致读取失败。

    Args:
        text: 文件文本内容。
        key_name: 目标 key 名（默认 DASHSCOPE_API_KEY）。

    Returns:
        解析到的 key 列表（去重、保持顺序）。
    """

    keys: List[str] = []
    seen = set()

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # 兼容 bash 的 export 前缀
        if line.lower().startswith("export "):
            line = line[7:].lstrip()

        val: str | None = None
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = _strip_wrapping_quotes(v)

            # 如果是目标 key，直接收集
            if k == key_name:
                val = v
            # 兼容：允许用 default 指定默认 key
            elif k.lower() in {"default", "api_key", "apikey", "key"}:
                val = v
            else:
                # 其它键忽略（允许同一文件包含多种服务 key）
                val = None
        else:
            # 한行一个 key
            val = _strip_wrapping_quotes(line)

        if val and val.strip():
            vv = val.strip()
            if vv not in seen:
                keys.append(vv)
                seen.add(vv)

    return keys


def load_api_key_from_config(
    config_path: str | Path = DEFAULT_CONFIG_RELATIVE_PATH,
    *,
    env_var_name: str = "DASHSCOPE_API_KEY",
    pick: int = 0,
) -> str:
    """从密钥文件加载 API Key（不使用环境变量）。

    说明：
    - 你明确要求不使用环境变量，避免在进程全局泄露或误用。
    - 本函数仅从 `config.json` 的 `secrets_file` 指向的文件读取。
    - secrets_file 既可以是 `.env` 风格（KEY=VALUE），也可以是“API-Keys.txt”风格（一行一个 key）。

    Args:
        config_path: 调度配置文件路径。
        env_var_name: 逻辑上的 key 名（历史兼容字段名，默认 DASHSCOPE_API_KEY）。
        pick: 当文件包含多个 key 时，选择第几个（从 0 开始）。

    Returns:
        API Key 字符串。

    Raises:
        ValueError: 未能找到 API Key。
        FileNotFoundError: 指定了密钥文件但文件不可用。
    """

    secrets_path = resolve_secrets_file_path(config_path)
    if secrets_path is None:
        raise ValueError("配置文件未提供 secrets_file，无法加载 API Key。")

    text = secrets_path.read_text(encoding="utf-8-sig")

    # 先用更通用的多 key 解析器，拿到候选 key 列表。
    keys = _parse_api_keys_text(text, key_name=env_var_name)
    if keys:
        idx = int(pick)
        if idx < 0 or idx >= len(keys):
            raise ValueError(f"密钥文件包含 {len(keys)} 个 key，但 pick={idx} 超出范围：{secrets_path}")
        return keys[idx]

    # 兼容旧逻辑：严格按 .env 解析并取指定字段。
    kv = _parse_dotenv_file(secrets_path)
    v2 = (kv.get(env_var_name) or "").strip()
    if v2:
        return v2

    raise ValueError(f"密钥文件中未找到可用的 API Key：{secrets_path}")

