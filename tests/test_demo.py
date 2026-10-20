"""演示服务的数据装载与路径安全。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from langchain_md_chunker import ChunkConfig, Chunker, write_chunks

SERVER_PATH = Path(__file__).resolve().parents[1] / "demo" / "server.py"


def load_demo_module():
    spec = importlib.util.spec_from_file_location("chunk_demo_server", SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


demo = load_demo_module()


@pytest.fixture()
def store(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "page.md").write_text("# Title\n\nbody text\n", encoding="utf-8")
    chunks = Chunker().split_directory(docs)
    write_chunks(chunks, tmp_path / "chunks", manifest={"source_root": str(docs)})
    return demo.ChunkStore(tmp_path / "chunks")


def test_store_loads_chunks_and_docs(store) -> None:
    assert store.chunks
    assert store.stats()["doc_count"] == 1
    assert store.has_doc("page.md")
    assert "body text" in store.read_doc("page.md")
    assert store.chunks[0]["preview"]


def test_read_doc_rejects_path_escape(store, tmp_path: Path) -> None:
    (tmp_path / "secret.md").write_text("secret\n", encoding="utf-8")

    with pytest.raises(PermissionError):
        store.read_doc("../secret.md")


def test_reload_tolerates_half_written_store(store, tmp_path: Path) -> None:
    before = len(store.chunks)
    path = tmp_path / "chunks" / "chunks.jsonl"
    path.write_text('{"id": "broken"\n', encoding="utf-8")

    store.reload()  # 不应抛异常

    assert len(store.chunks) == before, "解析失败时应保留上一份快照"


def test_reload_picks_up_new_store(store, tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "second.md").write_text("# Second\n\nmore content\n", encoding="utf-8")
    write_chunks(Chunker().split_directory(docs), tmp_path / "chunks")

    store.reload()

    assert store.has_doc("second.md")


def test_preview_uses_content_when_present(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "page.md").write_text("# 1\n\n## 2\n\nbody\n", encoding="utf-8")
    chunks = Chunker(ChunkConfig(include_headings=True)).split_directory(docs)
    write_chunks(chunks, tmp_path / "chunks", manifest={"source_root": str(docs)})

    store = demo.ChunkStore(tmp_path / "chunks")

    assert store.chunks[0]["preview"].startswith("# 1")
    assert "content" not in store.chunks[0]


def test_manifest_stats_are_served(store) -> None:
    assert json.dumps(store.stats())
    assert store.source_root.is_dir()
