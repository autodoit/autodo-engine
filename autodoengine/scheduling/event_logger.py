"""调度事件日志模块。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from autodoengine.scheduling.types import DispatchEvent


@dataclass(slots=True)
class DispatchEventLogger:
    """调度事件日志器。"""

    log_path: Path

    def emit(self, event: DispatchEvent) -> None:
        """写入单条事件日志。"""

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

