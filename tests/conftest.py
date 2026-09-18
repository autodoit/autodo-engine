"""pytest 全局夹具。

`sync_affair_databases` 每次都会把"官方事务库缓存"写回引擎仓被 git 跟踪的
`config/affair_registry.json`（见 affair_sync.default_aok_db_path）。
这在生产是预期行为，但会让任何触发同步的测试脏改仓库文件、污染 CI 工作树。

autouse 夹具在整场测试内把该路径重定向到临时目录，保证测试绝不写仓库跟踪配置。
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from autodoengine.utils.common import affair_sync


@pytest.fixture(scope="session", autouse=True)
def isolate_official_registry_path() -> Iterator[Path]:
    """把官方库写入路径重定向到会话级临时文件。

    Yields:
        重定向后的临时官方库路径。
    """

    with tempfile.TemporaryDirectory() as temp_dir:
        fake_db = Path(temp_dir) / "affair_registry.json"
        original = affair_sync.default_aok_db_path
        affair_sync.default_aok_db_path = lambda: fake_db  # type: ignore[assignment]
        try:
            yield fake_db
        finally:
            affair_sync.default_aok_db_path = original  # type: ignore[assignment]
