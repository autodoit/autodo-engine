"""
Skill 渲染引擎工具。
用于解析和渲染符合特定规范的 SKILL.md 文件（包含 YAML frontmatter 和 Jinja2 模板）。
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateSyntaxError

class SkillRenderer:
    """
    Skill 文件渲染器类。
    
    Attributes:
        env: Jinja2 环境对象，配置为严格模式。
    """

    def __init__(self, search_paths: Optional[List[str]] = None):
        """
        初始化渲染器。
        
        Args:
            search_paths: Jinja2 模板搜索路径列表。
        """
        loader = FileSystemLoader(search_paths) if search_paths else None
        self.env = Environment(
            loader=loader,
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )
        self.env.filters["to_json"] = lambda x: json.dumps(x, ensure_ascii=False)

    def load_skill(self, skill_path: str) -> Tuple[Dict[str, Any], str]:
        """
        加载并解析 Skill 文件内容。
        """
        path = Path(skill_path)
        if not path.exists():
            raise FileNotFoundError(f"找不到 Skill 文件: {skill_path}")

        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            raise ValueError(f"Skill 文件 {skill_path} 必须以 \"---\" 开头的 YAML frontmatter 起始。")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Skill 文件 {skill_path} 格式错误，未能找到闭合的 \"---\"。")

        try:
            meta = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"解析 Skill 元数据失败: {e}")

        body = parts[2].strip()
        return meta, body

    def validate_params(self, meta: Dict[str, Any], params: Dict[str, Any]) -> List[str]:
        """
        根据元数据校验输入参数。
        """
        missing = []
        inputs_config = meta.get("inputs", {})
        if not isinstance(inputs_config, dict):
            return []

        for param_name, config in inputs_config.items():
            if not isinstance(config, dict):
                continue
            if config.get("required", False) and param_name not in params:
                missing.append(param_name)
        return missing

    def render(self, skill_path: str, params: Dict[str, Any]) -> str:
        """
        执行渲染逻辑。
        """
        meta, body = self.load_skill(skill_path)
        missing = self.validate_params(meta, params)
        if missing:
            msg = ", ".join(missing)
            raise ValueError(f"渲染 Skill 失败，缺少必需参数: {msg}")

        try:
            template = self.env.from_string(body)
            return template.render(**params)
        except TemplateSyntaxError as e:
            raise ValueError(f"Skill 模板语法错误 (行 {e.lineno}): {e.message}")
        except Exception as e:
            raise ValueError(f"渲染过程出错: {e}")

def render_skill_prompt(skill_path: str, params: Dict[str, Any], search_paths: Optional[List[str]] = None) -> str:
    """
    便捷函数：渲染 Skill 得到 Prompt。
    """
    renderer = SkillRenderer(search_paths=search_paths)
    return renderer.render(skill_path, params)
