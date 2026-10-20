"""文件/目录级 API、偏移校验、编码边界与确定性。"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from langchain_md_chunker import Chunk, ChunkConfig, Chunker, verify_chunks


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_split_file_uses_path_relative_to_root(tmp_path: Path) -> None:
    target = write(tmp_path / "oss" / "python" / "page.md", "# T\n\nbody\n")

    chunks = Chunker().split_file(target, root=tmp_path)

    assert chunks
    assert chunks[0].doc == "oss/python/page.md"


def test_split_file_defaults_root_to_parent(tmp_path: Path) -> None:
    target = write(tmp_path / "page.md", "# T\n\nbody\n")

    assert Chunker().split_file(target)[0].doc == "page.md"


def test_split_file_falls_back_to_name_outside_root(tmp_path: Path) -> None:
    target = write(tmp_path / "page.md", "# T\n\nbody\n")

    chunks = Chunker().split_file(target, root=tmp_path / "elsewhere")

    assert chunks[0].doc == "page.md"


def test_split_directory_filters_and_is_stable(tmp_path: Path) -> None:
    write(tmp_path / "b.md", "# B\n\nb body\n")
    write(tmp_path / "a" / "a.md", "# A\n\na body\n")
    write(tmp_path / "skip.txt", "# not markdown\n")
    chunker = Chunker()

    first = chunker.split_directory(tmp_path)
    second = chunker.split_directory(tmp_path)

    assert [chunk.doc for chunk in first] == [chunk.doc for chunk in second]
    assert {chunk.doc for chunk in first} == {"a/a.md", "b.md"}


def test_split_directory_custom_patterns(tmp_path: Path) -> None:
    write(tmp_path / "page.md", "# T\n\nbody\n")
    write(tmp_path / "page.mdx", "# T\n\nbody\n")

    only_mdx = Chunker().split_directory(tmp_path, patterns=("*.mdx",))

    assert {chunk.doc for chunk in only_mdx} == {"page.mdx"}


def test_split_directory_matches_uppercase_suffix(tmp_path: Path) -> None:
    write(tmp_path / "PAGE.MD", "# Upper\n\nbody\n")

    docs = [chunk.doc for chunk in Chunker().split_directory(tmp_path)]

    assert docs == ["PAGE.MD"]


def test_split_directory_skips_dependency_directories(tmp_path: Path) -> None:
    write(tmp_path / "keep.md", "# Keep\n\nbody\n")
    write(tmp_path / "node_modules" / "pkg" / "noise.md", "# Noise\n\nbody\n")
    write(tmp_path / ".venv" / "lib" / "noise.md", "# Noise\n\nbody\n")

    docs = [chunk.doc for chunk in Chunker().split_directory(tmp_path)]

    assert docs == ["keep.md"]


def test_split_directory_rejects_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        Chunker().split_directory(tmp_path / "missing")


def test_verify_chunks_passes_and_detects_tampering(tmp_path: Path) -> None:
    target = write(tmp_path / "page.md", "# T\n\nbody text here\n")
    chunks = Chunker().split_file(target, root=tmp_path)

    assert verify_chunks(chunks, tmp_path) == []

    tampered = replace(chunks[0], text=chunks[0].text + "tampered")
    assert len(verify_chunks([tampered], tmp_path)) == 1

    out_of_range = replace(chunks[0], start=10_000, end=20_000, text="")
    problems = verify_chunks([out_of_range], tmp_path)
    assert len(problems) == 1
    assert "out of range" in problems[0]


def test_chunk_without_content_defaults_to_text() -> None:
    chunk = Chunk(
        id="c1",
        doc="a.md",
        start=0,
        end=4,
        start_line=1,
        end_line=1,
        headings=("T",),
        context="T",
        text="body",
    )

    assert chunk.content == "body"
    assert chunk.to_dict()["content"] == "body"


def test_verify_chunks_reports_missing_source(tmp_path: Path) -> None:
    body = "\n\n".join(["body " * 40] * 2)
    target = write(tmp_path / "page.md", f"# T\n\n{body}\n")
    chunks = Chunker(ChunkConfig(max_chars=200)).split_file(target, root=tmp_path)
    assert len(chunks) > 1
    target.unlink()

    problems = verify_chunks(chunks, tmp_path)

    # 同一文档只报告一次，后续 chunk 不再重复读取
    assert len(problems) == 1
    assert "cannot read" in problems[0]


def test_split_directory_orders_by_posix_path(tmp_path: Path) -> None:
    write(tmp_path / "b.md", "# B\n\nb\n")
    write(tmp_path / "a" / "z.md", "# Z\n\nz\n")
    write(tmp_path / "a.md", "# A\n\na\n")

    docs = [chunk.doc for chunk in Chunker().split_directory(tmp_path)]

    # as_posix 排序："a.md" < "a/z.md" < "b.md"（Path 默认排序会先排子目录）
    assert docs == ["a.md", "a/z.md", "b.md"]


def test_unicode_offsets_are_code_points(tmp_path: Path) -> None:
    text = (
        "# \u6807\u9898\n\n"
        "\u4e2d\u6587\u6bb5\u843d\uff0c\u542b emoji \U0001F680 \u4e0e e\u0301\u3002\n"
    )
    target = write(tmp_path / "unicode.md", text)
    # UTF-8 字节数明显大于码点数，字节偏移不能直接当字符偏移用
    assert len(text.encode("utf-8")) > len(text)

    chunks = Chunker(ChunkConfig(max_chars=30)).split_file(target, root=tmp_path)

    for chunk in chunks:
        assert text[chunk.start : chunk.end] == chunk.text
    assert any("\U0001F680" in chunk.text for chunk in chunks)
    assert verify_chunks(chunks, tmp_path) == []


def test_crlf_offsets_and_line_numbers() -> None:
    text = "# T\r\n\r\npara\r\n\r\n```py\r\nx = 1\r\n```\r\n"
    chunks = Chunker(ChunkConfig(max_chars=1000)).split_text(text, doc="crlf.md")

    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 7
    assert text[chunks[0].start : chunks[0].end] == chunks[0].text


def test_chunk_ids_are_stable_and_doc_scoped() -> None:
    text = "# T\n\nbody\n"

    first = Chunker().split_text(text, doc="a.md")
    again = Chunker().split_text(text, doc="a.md")
    other_doc = Chunker().split_text(text, doc="b.md")

    assert [chunk.id for chunk in first] == [chunk.id for chunk in again]
    assert first[0].id != other_doc[0].id
    assert all(chunk.id.startswith("c") for chunk in first)


def test_split_text_default_doc_and_empty_input() -> None:
    assert Chunker().split_text("# T\n\nbody\n")[0].doc == "<memory>"
    assert Chunker().split_text("") == []


def test_content_equals_text_by_default() -> None:
    chunks = Chunker().split_text("# 1\n\n## 2\n\n### 3\n\nxxxx\n")

    assert chunks
    assert all(chunk.content == chunk.text for chunk in chunks)


def test_chunk_records_dominant_kind_and_language() -> None:
    fenced = Chunker(ChunkConfig(max_chars=1000)).split_text(
        "# T\n\n```python\nprint(1)\n```\n"
    )
    assert fenced[0].kind == "code"
    assert fenced[0].lang == "python"

    table = Chunker().split_text("# T\n\n| a | b |\n| - | - |\n")
    assert table[0].kind == "table"

    mixed = Chunker(ChunkConfig(max_chars=1000)).split_text(
        "# T\n\nparagraph\n\n```python\nprint(1)\n```\n"
    )
    assert mixed[0].kind == "mixed"
    assert mixed[0].lang == ""

    paragraph = Chunker().split_text("# T\n\nbody\n")[0]
    assert paragraph.kind == "para"
    assert paragraph.lang == ""


def test_include_headings_does_not_duplicate_own_heading() -> None:
    text = "# 1\n\n## 2\n\n### 3\n\nxxxx\n"
    chunks = Chunker(ChunkConfig(include_headings=True)).split_text(text)

    assert len(chunks) == 1
    assert chunks[0].text == "### 3\n\nxxxx"
    assert chunks[0].content == "# 1\n## 2\n\n### 3\n\nxxxx"


def test_include_headings_prefixes_chunks_without_their_heading() -> None:
    body = "\n\n".join(["a" * 100] * 3)
    text = "# 1\n\n## 2\n\n" + body + "\n"
    chunks = Chunker(ChunkConfig(max_chars=150, include_headings=True)).split_text(text)

    assert len(chunks) >= 2
    assert chunks[0].text.startswith("## 2")
    assert chunks[0].content.startswith("# 1\n\n## 2")
    assert not chunks[1].text.startswith("#")
    assert chunks[1].content.startswith("# 1\n## 2\n\n")
    assert chunks[1].content.endswith(chunks[1].text)


def test_include_headings_keeps_original_heading_levels() -> None:
    body = "\n\n".join(["b" * 100] * 2)
    text = "# A\n\n### C\n\n" + body + "\n"
    chunks = Chunker(ChunkConfig(max_chars=120, include_headings=True)).split_text(text)

    later = [chunk for chunk in chunks if not chunk.text.startswith("#")]
    assert later
    assert later[0].content.startswith("# A\n### C\n\n")


def test_include_headings_skips_empty_titles() -> None:
    text = "# A\n\n## \n\n### C\n\nbody\n"
    chunks = Chunker(ChunkConfig(include_headings=True)).split_text(text)

    assert len(chunks) == 1
    assert chunks[0].content == "# A\n\n### C\n\nbody"


def test_include_headings_without_headings_is_a_no_op() -> None:
    chunks = Chunker(ChunkConfig(include_headings=True)).split_text("just text\n")

    assert chunks[0].content == chunks[0].text


def test_include_headings_after_dropped_heading_resync() -> None:
    text = "# 1\n\n## 2\n\nexport const x = 1;\n\nbody text\n"
    chunks = Chunker(ChunkConfig(include_headings=True)).split_text(text)

    assert len(chunks) == 1
    assert chunks[0].text == "body text"
    assert chunks[0].content == "# 1\n## 2\n\nbody text"


def test_chunk_ids_are_16_hex(tmp_path: Path) -> None:
    chunks = Chunker().split_text("# T\n\nbody\n", doc="a.md")

    assert re.fullmatch(r"c[0-9a-f]{16}", chunks[0].id)


def test_content_id_is_stable_across_documents() -> None:
    chunker = Chunker(ChunkConfig(id_strategy="content"))
    first = chunker.split_text("# T\n\nbody\n", doc="a.md")[0]
    second = chunker.split_text("# T\n\nbody\n", doc="b.md")[0]
    other = chunker.split_text("# T\n\nother\n", doc="c.md")[0]

    assert first.id == second.id
    assert first.id != other.id


def test_content_id_follows_the_content_not_the_offsets() -> None:
    chunker = Chunker(ChunkConfig(id_strategy="content"))
    first = chunker.split_text("Intro.\n\n# T\n\nbody\n", doc="a.md")
    moved = chunker.split_text("# T\n\nbody\n", doc="a.md")

    tail = next(chunk for chunk in first if chunk.text == "# T\n\nbody")
    assert tail.id == moved[0].id


def test_invalid_id_strategy_is_rejected() -> None:
    with pytest.raises(ValueError, match="id_strategy"):
        ChunkConfig(id_strategy="uuid")


def test_split_file_honours_encoding(tmp_path: Path) -> None:
    target = tmp_path / "latin.md"
    target.write_bytes("# T\n\ncafé\n".encode("latin-1"))

    chunks = Chunker().split_file(target, encoding="latin-1")

    assert "café" in chunks[0].text
    with pytest.raises(UnicodeDecodeError):
        Chunker().split_file(target)


def test_split_directory_can_skip_unreadable_files(tmp_path: Path) -> None:
    write(tmp_path / "good.md", "# Good\n\nbody\n")
    (tmp_path / "bad.md").write_bytes(b"# Bad\n\n\xff\xfe\n")

    with pytest.raises(UnicodeDecodeError):
        Chunker().split_directory(tmp_path)

    chunks = Chunker().split_directory(tmp_path, on_error="skip")

    assert [chunk.doc for chunk in chunks] == ["good.md"]


def test_iter_directory_streams_in_the_same_order(tmp_path: Path) -> None:
    write(tmp_path / "b.md", "# B\n\nbody\n")
    write(tmp_path / "a.md", "# A\n\nbody\n")
    chunker = Chunker()

    iterator = chunker.iter_directory(tmp_path)

    assert iter(iterator) is iterator
    assert [chunk.doc for chunk in iterator] == [
        chunk.doc for chunk in chunker.split_directory(tmp_path)
    ]
    assert [chunk.doc for chunk in chunker.iter_directory(tmp_path)] == ["a.md", "b.md"]


def test_invalid_on_error_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="on_error"):
        Chunker().split_directory(tmp_path, on_error="warn")


def test_iter_directory_validates_before_iteration(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        Chunker().iter_directory(tmp_path / "missing")
    with pytest.raises(ValueError, match="on_error"):
        Chunker().iter_directory(tmp_path, on_error="warn")


def test_verify_chunks_honours_encoding(tmp_path: Path) -> None:
    target = tmp_path / "latin.md"
    target.write_bytes("# T\n\ncafé\n".encode("latin-1"))
    chunks = Chunker().split_file(target, root=tmp_path, encoding="latin-1")

    assert verify_chunks(chunks, tmp_path, encoding="latin-1") == []
    problems = verify_chunks(chunks, tmp_path)
    assert len(problems) == 1
    assert "cannot read" in problems[0]
