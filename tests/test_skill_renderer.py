import os
import pytest
from autodoengine.utils.skill_renderer import SkillRenderer, render_skill_prompt

# 模拟一个符合规范的 SKILL.md 文件内容
MOCK_SKILL_CONTENT = """---
name: "mock-skill"
description: "A test skill for validating renderer."
inputs:
  user_name:
    description: "The name of the user."
    required: true
  task_list:
    description: "A list of tasks."
    required: false
---
Hello, {{ user_name }}!
{% if task_list %}
Your tasks:
{% for task in task_list %}
- {{ task }}
{% endfor %}
{% else %}
You have no tasks pending.
{% endif %}
"""

@pytest.fixture
def temp_skill_file(tmp_path):
    skill_dir = tmp_path / "mock_skills"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(MOCK_SKILL_CONTENT, encoding="utf-8")
    return str(skill_file)

def test_load_skill(temp_skill_file):
    renderer = SkillRenderer()
    meta, body = renderer.load_skill(temp_skill_file)
    
    assert meta["name"] == "mock-skill"
    assert "Hello, {{ user_name }}!" in body
    assert "--- " not in body

def test_validate_params():
    renderer = SkillRenderer()
    meta = {
        "inputs": {
            "user_name": {"required": True},
            "extra_info": {"required": False}
        }
    }
    
    # 全部满足
    assert renderer.validate_params(meta, {"user_name": "Ethan"}) == []
    # 缺少必需参数
    assert renderer.validate_params(meta, {"extra_info": "something"}) == ["user_name"]
    # 没有输入配置时，不应报错且应返回空列表
    assert renderer.validate_params({}, {"any": "thing"}) == []

def test_full_render(temp_skill_file):
    params = {
        "user_name": "Ethan",
        "task_list": ["Task 1", "Task 2"]
    }
    
    rendered_text = render_skill_prompt(temp_skill_file, params)
    
    assert "Hello, Ethan!" in rendered_text
    assert "- Task 1" in rendered_text
    assert "- Task 2" in rendered_text

def test_render_missing_params(temp_skill_file):
    renderer = SkillRenderer()
    # 故意不传 user_name（它是必需的）
    with pytest.raises(ValueError, match="渲染 Skill 失败，缺少必需参数: user_name"):
        renderer.render(temp_skill_file, {"task_list": []})

def test_render_strict_undefined(temp_skill_file):
    renderer = SkillRenderer()
    # 传入了 user_name，但如果在 body 里引用了一个没在 meta/params 里定义的变量
    # 注意：我们的 mock 模板里引用了 task_list，如果在 params 里没传且没默认值，会被 StrictUndefined 拦截。
    # 这里我们传入所有必需的，但包含一个不在 params 里的变量 undefined_var
    body_with_undefined = MOCK_SKILL_CONTENT + "\nCheck: {{ undefined_var }}"
    
    import yaml
    from pathlib import Path
    custom_skill = Path(temp_skill_file).parent / "custom_undef.md"
    custom_skill.write_text(body_with_undefined, encoding="utf-8")
    
    # 确保同时传入 task_list 避免它先报错
    with pytest.raises(ValueError, match="'undefined_var' is undefined"):
        renderer.render(str(custom_skill), {"user_name": "Ethan", "task_list": []})
