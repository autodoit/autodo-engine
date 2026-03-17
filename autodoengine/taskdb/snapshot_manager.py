"""快照管理模块。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(slots=True)
class SnapshotManager:
    """快照管理器。"""

    tasks_root: Path
    snapshot_root: Path

    def create_snapshot(self) -> str:
        """创建当前任务数据库快照。"""

        snapshot_id = f"snapshot-{uuid4().hex[:12]}"
        target_dir = self.snapshot_root / snapshot_id
        target_dir.mkdir(parents=True, exist_ok=True)
        for path in self.tasks_root.iterdir():
            if path.name == self.snapshot_root.name:
                continue
            destination = target_dir / path.name
            if path.is_dir():
                shutil.copytree(path, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(path, destination)
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> None:
        """从快照恢复任务数据库。"""

        source_dir = self.snapshot_root / snapshot_id
        if not source_dir.exists():
            raise FileNotFoundError(f"找不到快照：{snapshot_id}")
        for path in source_dir.iterdir():
            destination = self.tasks_root / path.name
            if path.is_dir():
                shutil.copytree(path, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(path, destination)
