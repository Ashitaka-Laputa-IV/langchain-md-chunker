"""包级入口与公开 API 的冒烟测试。"""

from __future__ import annotations

import pytest

import langchain_md_chunker
from langchain_md_chunker import cli


def test_console_entrypoint_delegates_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_main() -> int:
        calls.append(1)
        return 0

    monkeypatch.setattr(cli, "main", fake_main)

    with pytest.raises(SystemExit) as excinfo:
        langchain_md_chunker.main()

    assert excinfo.value.code == 0
    assert calls == [1]


def test_public_api_is_exported() -> None:
    for name in (
        "Chunk",
        "ChunkConfig",
        "Chunker",
        "parse_blocks",
        "split_text",
        "verify_chunks",
        "write_chunks",
        "read_chunks",
        "build_manifest",
        "read_manifest",
    ):
        assert hasattr(langchain_md_chunker, name)
        assert name in langchain_md_chunker.__all__
