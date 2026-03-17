"""CSV 与 JSON 产物存储模块。"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from autodoengine.taskdb.schema_registry import TableSchema


@dataclass(slots=True)
class CsvStore:
    """CSV 存储器。"""

    file_path: Path
    schema: TableSchema

    def ensure_exists(self) -> None:
        """确保 CSV 文件存在且带表头。"""

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if self.file_path.exists():
            return
        self.write_rows(rows=[])

    def read_rows(self) -> list[dict[str, str]]:
        """读取所有行。"""

        if not self.file_path.exists():
            return []
        with self.file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]

    def write_rows(self, rows: list[dict[str, Any]]) -> None:
        """原子写入全部行。"""

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, encoding="utf-8", newline="", dir=self.file_path.parent) as tmp:
            writer = csv.DictWriter(tmp, fieldnames=self.schema.headers)
            writer.writeheader()
            for row in rows:
                normalized_row = {
                    header: str(row.get(header, self._default_for(header)))
                    for header in self.schema.headers
                }
                writer.writerow(normalized_row)
            temp_path = Path(tmp.name)
        temp_path.replace(self.file_path)

    def append_row(self, row: dict[str, Any]) -> None:
        """追加一行记录。"""

        rows = self.read_rows()
        rows.append(row)
        self.write_rows(rows)

    def _default_for(self, header: str) -> str:
        """获取列默认值。"""

        for column in self.schema.columns:
            if column.name == header:
                return column.default
        return ""


@dataclass(slots=True)
class JsonArtifactStore:
    """JSON/JSONL 产物存储器。"""

    file_path: Path

    def write_json(self, payload: dict[str, Any]) -> None:
        """写入 JSON 文件。"""

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read_json(self) -> dict[str, Any]:
        """读取 JSON 文件。"""

        if not self.file_path.exists():
            return {}
        return json.loads(self.file_path.read_text(encoding="utf-8"))

    def append_jsonl(self, payload: dict[str, Any]) -> None:
        """追加 JSONL 记录。"""

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

