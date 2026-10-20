"""Tests for the chunker core: offsets, structure, and real-corpus invariants."""

from __future__ import annotations

from pathlib import Path

import pytest

from langchain_md_chunker import ChunkConfig, Chunker, parse_blocks, split_text, verify_chunks

CORPUS = Path(__file__).resolve().parents[1] / "data" / "langchain-docs"


def test_chunk_text_matches_source_offsets() -> None:
    text = (
        "# Title\n\n"
        "Intro paragraph that is long enough to matter.\n\n"
        "## Section\n\n"
        "Body text.\n\n"
        "```python\nprint('hi')\n```\n\n"
        "Tail text.\n"
    )
    chunks = Chunker(ChunkConfig(max_chars=120, min_chars=0)).split_text(text)

    assert chunks
    for chunk in chunks:
        assert text[chunk.start : chunk.end] == chunk.text
        assert chunk.chars == len(chunk.text)


def test_heading_path_is_tracked_as_context() -> None:
    text = "# A\n\nintro\n\n## B\n\nb body\n\n### C\n\nc body\n"
    chunks = Chunker(ChunkConfig(max_chars=500, min_chars=0)).split_text(text)

    assert [chunk.headings for chunk in chunks] == [("A",), ("A", "B"), ("A", "B", "C")]
    assert [chunk.context for chunk in chunks] == ["A", "A > B", "A > B > C"]
    assert chunks[1].text.startswith("## B")
    assert chunks[2].text.startswith("### C")


def test_code_fence_stays_inside_one_chunk_when_it_fits() -> None:
    text = "# T\n\nSome intro.\n\n```python\nprint(1)\nprint(2)\n```\n\nAfter.\n"
    chunks = Chunker(ChunkConfig(max_chars=1000, min_chars=0)).split_text(text)

    fenced = [chunk for chunk in chunks if "```python" in chunk.text]
    assert len(fenced) == 1
    assert fenced[0].text.count("```") == 2


def test_oversized_code_fence_splits_on_line_boundaries() -> None:
    body = "\n".join(f"print({index})" for index in range(400))
    text = "# T\n\n```python\n" + body + "\n```\n"
    chunks = Chunker(ChunkConfig(max_chars=400, min_chars=0)).split_text(text)

    assert len(chunks) > 1
    assert chunks[0].text.startswith("# T")
    assert "```python" in chunks[0].text
    assert chunks[-1].text.endswith("```")
    for chunk in chunks[1:]:
        assert chunk.chars <= 400


def test_single_long_line_terminates() -> None:
    text = "# T\n\n" + "x" * 5000 + "\n"
    chunks = Chunker(ChunkConfig(max_chars=200, min_chars=0)).split_text(text)

    assert len(chunks) == 1
    assert text[chunks[0].start : chunks[0].end] == chunks[0].text


def test_frontmatter_and_export_blocks_are_skipped() -> None:
    text = (
        "---\ntitle: x\n---\n\n"
        "# T\n\nexport const Map = ({active}) => {\n  return active;\n};\n\n"
        "Real content here.\n"
    )
    chunks = Chunker().split_text(text)

    assert len(chunks) == 1
    assert "title: x" not in chunks[0].text
    assert "export const" not in chunks[0].text
    assert "Real content here." in chunks[0].text


def test_boilerplate_prefixes_are_skipped() -> None:
    text = (
        "> ## Documentation Index\n> Fetch the complete index.\n\n"
        '<div className="source-links">\n  <Callout icon="edit">\n    [Edit](x)\n  </Callout>\n</div>\n\n'
        "# T\n\nreal content\n"
    )
    chunks = Chunker().split_text(text)

    assert len(chunks) == 1
    assert chunks[0].text == "# T\n\nreal content"

    kept = Chunker(ChunkConfig(skip_prefixes=())).split_text(text)
    assert len(kept) > len(chunks)


def test_heading_only_sections_do_not_create_chunks() -> None:
    text = "# A\n\n## B\n\nb body\n"
    chunks = Chunker(ChunkConfig(max_chars=500, min_chars=0)).split_text(text)

    assert len(chunks) == 1
    assert chunks[0].headings == ("A", "B")


def test_mdx_component_without_closing_tag_is_a_paragraph() -> None:
    text = "# T\n\n<Note>\n\ninside a note\n\n</Note>\n\n<br>\n\nend\n"
    blocks = parse_blocks(text)

    kinds = [block.kind for block in blocks]
    assert "mdx" in kinds
    assert text[blocks[-1].start : blocks[-1].end] == "end"


def test_block_offsets_cover_their_slice() -> None:
    text = "# T\n\npara\n\n```py\nx = 1\n```\n\n| a | b |\n| - | - |\n| 1 | 2 |\n"
    for block in parse_blocks(text):
        assert text[block.start : block.end].strip()


@pytest.mark.skipif(not CORPUS.is_dir(), reason="语料未下载：uv run python data/download_docs.py")
def test_corpus_chunks_are_consistent() -> None:
    config = ChunkConfig()
    chunks = Chunker(config).split_directory(CORPUS)

    assert chunks, "语料应至少产生一个 chunk"
    assert verify_chunks(chunks, CORPUS) == []

    by_doc: dict[str, list] = {}
    for chunk in chunks:
        assert chunk.text.strip()
        assert chunk.start < chunk.end
        assert chunk.id not in {item.id for item in by_doc.get(chunk.doc, [])}, "chunk id 冲突"
        by_doc.setdefault(chunk.doc, []).append(chunk)

    for doc_chunks in by_doc.values():
        for previous, current in zip(doc_chunks, doc_chunks[1:]):
            assert previous.end <= current.start, "chunk 不应重叠或乱序"


@pytest.mark.skipif(not CORPUS.is_dir(), reason="语料未下载：uv run python data/download_docs.py")
def test_corpus_chunk_sizes_are_reasonable() -> None:
    chunks = Chunker().split_directory(CORPUS)
    oversize = [chunk for chunk in chunks if chunk.chars > 1500]

    # 只有“标题 + 单个不可拆块（超长代码行 / 大型 MDX 组件）”允许突破上限
    for chunk in oversize:
        assert chunk.text.startswith("#") or "\n" not in chunk.text
    assert len(oversize) <= len(chunks) * 0.01


def test_split_text_handles_blank_input() -> None:
    assert split_text("") == []
    assert split_text("   \n\n  ") == []


def test_invalid_config_is_rejected() -> None:
    with pytest.raises(ValueError):
        ChunkConfig(max_chars=0)
    with pytest.raises(ValueError):
        ChunkConfig(max_chars=100, min_chars=200)
