"""文件/目录级 API、偏移校验、编码边界与确定性。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from langchain_md_chunker import ChunkConfig, Chunker, verify_chunks


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
    assert "超出文件长度" in problems[0]


def test_unicode_offsets_are_code_points(tmp_path: Path) -> None:
    text = "# \u6807\u9898\n\n\u4e2d\u6587\u6bb5\u843d\uff0c\u542b emoji \U0001F680 \u4e0e e\u0301\u3002\n"
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
