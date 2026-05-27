"""模板事务中文关键字入口测试。"""

from __future__ import annotations

import json
from pathlib import Path

from autodoengine.core.template_affair import TemplateAffairBase


class DemoTemplateAffair(TemplateAffairBase):
    """用于验证模板事务中文入口的最小样例。"""

    def __init__(self) -> None:
        super().__init__(affair_name="demo_template_affair")

    def run_business(self, *, config, workspace_root):
        output_dir = Path(config["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / "done.txt"
        target.write_text("ok\n", encoding="utf-8")
        return [target]


def test_template_affair_execute_should_accept_chinese_keyword_arguments(tmp_path: Path) -> None:
    """模板事务 execute/load_config 应支持中文关键字参数。"""

    config_path = tmp_path / "demo.json"
    config_path.write_text(
        json.dumps({"output_dir": str(tmp_path / "output")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    affair = DemoTemplateAffair()
    payload = affair.load_config(配置路径=config_path)
    assert payload["output_dir"] == str(tmp_path / "output")

    outputs = affair.execute(配置路径=config_path, 工作区根路径=tmp_path)
    assert len(outputs) == 1
    assert Path(outputs[0]).exists()
