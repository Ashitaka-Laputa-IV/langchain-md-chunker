"""包级入口、公开 API 与预设的冒烟测试。"""

from __future__ import annotations

import langchain_md_chunker
from langchain_md_chunker import ChunkConfig, cli, langchain_docs


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
        "langchain_docs",
    ):
        assert hasattr(langchain_md_chunker, name)
        assert name in langchain_md_chunker.__all__


def test_console_entrypoint_target_exists() -> None:
    assert callable(cli.main)
    assert callable(cli.build_parser)


def test_generic_config_has_no_corpus_boilerplate() -> None:
    assert ChunkConfig().skip_prefixes == ()


def test_langchain_docs_preset_drops_known_boilerplate() -> None:
    config = langchain_docs()

    assert config.skip_prefixes
    assert config.max_chars == 1500
    assert not config.include_headings

    custom = langchain_docs(max_chars=800, include_headings=True)
    assert custom.max_chars == 800
    assert custom.include_headings
    assert custom.skip_prefixes == config.skip_prefixes
