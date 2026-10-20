"""切分行为：偏移精确性、标题上下文、块打包与语料不变量。"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from langchain_md_chunker import (
    ChunkConfig,
    Chunker,
    parse_blocks,
    split_text,
    verify_chunks,
)


def test_chunk_text_matches_source_offsets() -> None:
    text = (
        "# Title\n\n"
        "Intro paragraph that is long enough to matter.\n\n"
        "## Section\n\n"
        "Body text.\n\n"
        "```python\nprint('hi')\n```\n\n"
        "Tail text.\n"
    )
    chunks = Chunker(ChunkConfig(max_chars=120)).split_text(text)

    assert chunks
    for chunk in chunks:
        assert text[chunk.start : chunk.end] == chunk.text
        assert chunk.chars == len(chunk.text)


def test_heading_path_is_tracked_as_context() -> None:
    text = "# A\n\nintro\n\n## B\n\nb body\n\n### C\n\nc body\n"
    chunks = Chunker(ChunkConfig(max_chars=500)).split_text(text)

    assert [chunk.headings for chunk in chunks] == [("A",), ("A", "B"), ("A", "B", "C")]
    assert [chunk.context for chunk in chunks] == ["A", "A > B", "A > B > C"]
    assert chunks[1].text.startswith("## B")
    assert chunks[2].text.startswith("### C")


def test_heading_level_jump_resets_the_stack() -> None:
    text = "# A\n\nintro a\n\n## B\n\nb body\n\n# C\n\nc body\n"
    chunks = Chunker(ChunkConfig(max_chars=500)).split_text(text)

    assert [chunk.headings for chunk in chunks] == [("A",), ("A", "B"), ("C",)]


def test_code_fence_stays_inside_one_chunk_when_it_fits() -> None:
    text = "# T\n\nSome intro.\n\n```python\nprint(1)\nprint(2)\n```\n\nAfter.\n"
    chunks = Chunker(ChunkConfig(max_chars=1000)).split_text(text)

    fenced = [chunk for chunk in chunks if "```python" in chunk.text]
    assert len(fenced) == 1
    assert fenced[0].text.count("```") == 2


def test_oversized_code_fence_splits_on_line_boundaries() -> None:
    body = "\n".join(f"print({index})" for index in range(400))
    text = "# T\n\n```python\n" + body + "\n```\n"
    chunks = Chunker(ChunkConfig(max_chars=400)).split_text(text)

    assert len(chunks) > 1
    assert chunks[0].text.startswith("# T")
    assert "```python" in chunks[0].text
    assert chunks[-1].text.endswith("```")
    for chunk in chunks[1:]:
        assert chunk.chars <= 400


def test_oversized_component_splits_between_children() -> None:
    children = "\n".join(
        f'  <Tab title="t{index}">\n'
        + "\n".join(f"    line {row}" for row in range(15))
        + "\n  </Tab>"
        for index in range(6)
    )
    text = f"# T\n\n<Tabs>\n{children}\n</Tabs>\n"
    chunks = Chunker(ChunkConfig(max_chars=400)).split_text(text)

    assert len(chunks) > 1
    # 首块含 <Tabs> 开头，其余块应从一个子元素开始，而不是从元素内部开始
    for chunk in chunks[1:]:
        assert chunk.text.lstrip().startswith(("<Tab", "</Tabs>"))


def test_single_long_line_terminates() -> None:
    text = "# T\n\n" + "x" * 5000 + "\n"
    chunks = Chunker(ChunkConfig(max_chars=200)).split_text(text)

    assert len(chunks) == 1
    assert text[chunks[0].start : chunks[0].end] == chunks[0].text


def test_blocks_are_packed_up_to_max_chars() -> None:
    text = "# T\n\n" + "\n\n".join(["a" * 100] * 5) + "\n"
    chunks = Chunker(ChunkConfig(max_chars=250)).split_text(text)

    assert len(chunks) == 3
    assert all(chunk.chars <= 250 for chunk in chunks)
    assert chunks[0].text.startswith("# T")


def test_skipped_block_breaks_the_chunk() -> None:
    text = "# T\n\n" + "a" * 120 + "\n\nexport const X = 1;\n\n" + "b" * 120 + "\n"
    chunks = Chunker(ChunkConfig(max_chars=1000)).split_text(text)

    assert len(chunks) == 2
    assert all("export const" not in chunk.text for chunk in chunks)


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
        '<div className="source-links">\n'
        '  <Callout icon="edit">\n'
        "    [Edit](x)\n"
        "  </Callout>\n"
        "</div>\n\n"
        "# T\n\nreal content\n"
    )
    chunks = Chunker().split_text(text)

    assert len(chunks) == 1
    assert chunks[0].text == "# T\n\nreal content"

    kept = Chunker(ChunkConfig(skip_prefixes=())).split_text(text)
    assert len(kept) > len(chunks)


def test_heading_only_sections_do_not_create_chunks() -> None:
    text = "# A\n\n## B\n\nb body\n"
    chunks = Chunker(ChunkConfig(max_chars=500)).split_text(text)

    assert len(chunks) == 1
    assert chunks[0].headings == ("A", "B")


def test_document_without_headings_has_empty_context() -> None:
    text = "just a paragraph\n\nand another one\n"
    chunks = Chunker().split_text(text)

    assert len(chunks) == 1
    assert chunks[0].headings == ()
    assert chunks[0].context == ""


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


def test_corpus_chunks_are_consistent(corpus_dir: Path, corpus_chunks) -> None:
    assert corpus_chunks, "语料应至少产生一个 chunk"
    assert verify_chunks(corpus_chunks, corpus_dir) == []
    assert len({chunk.id for chunk in corpus_chunks}) == len(corpus_chunks), "chunk id 应全局唯一"

    by_doc: dict[str, list] = {}
    for chunk in corpus_chunks:
        assert chunk.text.strip()
        assert chunk.start < chunk.end
        by_doc.setdefault(chunk.doc, []).append(chunk)

    for doc_chunks in by_doc.values():
        for previous, current in itertools.pairwise(doc_chunks):
            assert previous.end <= current.start, "chunk 不应重叠或乱序"


def test_corpus_chunk_sizes_are_reasonable(corpus_chunks) -> None:
    oversize = [chunk for chunk in corpus_chunks if chunk.chars > 1500]

    # 只有“标题 + 单个不可拆块（超长代码行 / 大型 MDX 组件）”允许突破上限
    for chunk in oversize:
        assert chunk.text.startswith("#") or "\n" not in chunk.text
    assert len(oversize) <= len(corpus_chunks) * 0.01


def test_split_text_handles_blank_input() -> None:
    assert split_text("") == []
    assert split_text("   \n\n  ") == []


def test_invalid_config_is_rejected() -> None:
    with pytest.raises(ValueError):
        ChunkConfig(max_chars=0)
    with pytest.raises(ValueError):
        ChunkConfig(skip_prefixes=("  ",))
