"""JSONL 与 manifest 的读写往返。"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_md_chunker import (
    CHUNKS_FILE,
    MANIFEST_FILE,
    Chunk,
    ChunkConfig,
    Chunker,
    build_manifest,
    read_chunks,
    read_manifest,
    write_chunks,
)

BODY = "\n\n".join(" ".join(f"word{index}_{row}" for index in range(6)) for row in range(12))


def make_chunks() -> list[Chunk]:
    chunker = Chunker(ChunkConfig(max_chars=120))
    return chunker.split_text(f"# Title\n\n{BODY}\n", doc="oss/page.md")


def test_write_read_roundtrip(tmp_path: Path) -> None:
    chunks = make_chunks()
    assert len(chunks) > 1

    chunks_path, manifest_path = write_chunks(chunks, tmp_path, manifest={"k": 1})

    assert chunks_path.name == CHUNKS_FILE
    assert manifest_path.name == MANIFEST_FILE
    assert read_chunks(tmp_path) == chunks
    assert read_chunks(chunks_path) == chunks
    assert read_manifest(tmp_path) == {"k": 1}


def test_jsonl_is_one_object_per_line_and_utf8(tmp_path: Path) -> None:
    text = "# \u6807\u9898\n\n\u6b63\u6587\n"
    chunks = Chunker().split_text(text, doc="u.md")

    path, _ = write_chunks(chunks, tmp_path)
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    assert len(lines) == len(chunks)
    assert "\u6807\u9898" in raw
    assert raw.endswith("\n")
    for line in lines:
        payload = json.loads(line)
        assert payload["doc"] == "u.md"
        assert payload["text"] == text[payload["start"] : payload["end"]]


def test_read_chunks_ignores_blank_lines(tmp_path: Path) -> None:
    path, _ = write_chunks(make_chunks(), tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n  \n")

    assert read_chunks(path) == make_chunks()


def test_write_without_manifest_leaves_it_absent(tmp_path: Path) -> None:
    write_chunks(make_chunks(), tmp_path)

    assert not (tmp_path / MANIFEST_FILE).exists()
    assert read_manifest(tmp_path) == {}


def test_write_empty_store(tmp_path: Path) -> None:
    _, manifest_path = write_chunks([], tmp_path, manifest={"chunk_count": 0})

    assert read_chunks(tmp_path) == []
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["chunk_count"] == 0


def test_build_manifest_summarises() -> None:
    chunks = make_chunks()
    config = ChunkConfig(max_chars=120)

    manifest = build_manifest(chunks, source_root="data/langchain-docs", config=config)

    assert manifest["doc_count"] == 1
    assert manifest["chunk_count"] == len(chunks)
    assert manifest["total_chars"] == sum(chunk.chars for chunk in chunks)
    assert manifest["chunk_chars_min"] <= manifest["chunk_chars_avg"] <= manifest["chunk_chars_max"]
    assert Path(manifest["source_root"]).is_absolute()
    assert manifest["config"]["max_chars"] == 120
    assert manifest["config"]["skip_prefixes"]


def test_chunk_dict_roundtrip() -> None:
    chunk = make_chunks()[0]

    restored = Chunk.from_dict(chunk.to_dict())

    assert restored == chunk
    assert restored.headings == chunk.headings
    assert restored.chars == len(restored.text)
