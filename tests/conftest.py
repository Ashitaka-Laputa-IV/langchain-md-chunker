"""共享 fixture：真实语料只下载一次，全量切分只跑一次。"""

from __future__ import annotations

from pathlib import Path

import pytest

from langchain_md_chunker import Chunker

CORPUS = Path(__file__).resolve().parents[1] / "data" / "langchain-docs"


@pytest.fixture(scope="session")
def corpus_dir() -> Path:
    if not CORPUS.is_dir():
        pytest.skip("语料未下载：uv run python data/download_docs.py")
    return CORPUS


@pytest.fixture(scope="session")
def corpus_chunks(corpus_dir: Path):
    return Chunker().split_directory(corpus_dir)
