"""解析层边界：围栏嵌套、围栏内伪标题、表格、MDX、分隔线。"""

from __future__ import annotations

from langchain_md_chunker import parse_blocks


def kinds(text: str) -> list[str]:
    return [block.kind for block in parse_blocks(text)]


def test_heading_inside_code_fence_is_not_a_heading() -> None:
    text = "# Real\n\n```python\n# not a heading\n## neither\n```\n\ntail\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["heading", "code", "para"]
    assert blocks[0].title == "Real"
    assert blocks[1].lang == "python"


def test_table_is_a_single_block() -> None:
    table = "| a | b |\n| - | - |\n| 1 | 2 |"
    text = table + "\n\nafter\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["table", "para"]
    assert text[blocks[0].start : blocks[0].end] == table


def test_longer_fence_wraps_shorter_fence() -> None:
    text = "````markdown\n```python\nprint(1)\n```\n````\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["code"]
    assert text[blocks[0].start : blocks[0].end].count("````") == 2


def test_tilde_fence_is_code() -> None:
    text = "~~~bash\necho hi\n~~~\n"
    blocks = parse_blocks(text)

    assert blocks[0].kind == "code"
    assert blocks[0].lang == "bash"


def test_unclosed_fence_runs_to_end_of_file() -> None:
    text = "# T\n\n```python\nprint(1)\n"
    blocks = parse_blocks(text)

    assert blocks[-1].kind == "code"
    assert text[blocks[-1].start : blocks[-1].end].rstrip().endswith("print(1)")


def test_mdx_component_is_one_block() -> None:
    text = '<Tabs>\n  <Tab title="A">\n\n    body\n\n  </Tab>\n</Tabs>\n'
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["mdx"]
    assert text[blocks[0].start : blocks[0].end] == text.rstrip("\n")


def test_self_closing_mdx_is_single_line() -> None:
    text = '<Card title="x" />\n\npara\n'
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["mdx", "para"]
    assert text[blocks[0].start : blocks[0].end] == '<Card title="x" />'


def test_list_rule_and_quote_blocks() -> None:
    text = "- one\n- two\n\n***\n\n> quoted\n\npara\n"

    assert kinds(text) == ["list", "rule", "quote", "para"]


def test_quote_block_keeps_inner_blank_line() -> None:
    text = "> first\n\n> second\n\npara\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["quote", "para"]
    assert text[blocks[0].start : blocks[0].end] == "> first\n\n> second"


def test_nested_component_with_same_tag_is_one_block() -> None:
    text = (
        '<Accordion title="outer">\n'
        '  <Accordion title="inner">\n    inner body\n  </Accordion>\n'
        "</Accordion>\n\nafter\n"
    )
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["mdx", "para"]
    assert text[blocks[0].start : blocks[0].end].endswith("</Accordion>")
    assert "inner body" in text[blocks[0].start : blocks[0].end]


def test_unclosed_component_stops_at_next_heading() -> None:
    text = "<Note>\n\n# Heading\n\ntail\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["para", "heading", "para"]
    assert text[blocks[1].start : blocks[1].end] == "# Heading"


def test_quote_ends_at_blank_line_followed_by_text() -> None:
    text = "> quoted\n\npara\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["quote", "para"]
    assert text[blocks[0].start : blocks[0].end] == "> quoted"


def test_unclosed_frontmatter_is_not_a_block() -> None:
    text = "---\ntitle: x\n\n# T\n\nbody\n"
    blocks = parse_blocks(text)

    assert blocks[0].kind != "frontmatter"
    assert any(block.kind == "heading" for block in blocks)


def test_single_line_document_without_trailing_newline() -> None:
    assert [block.kind for block in parse_blocks("just one paragraph")] == ["para"]
    assert [block.kind for block in parse_blocks("> just one quote")] == ["quote"]


def test_blocks_are_ordered_and_non_overlapping() -> None:
    text = (
        "# T\n\npara\n\n```py\nx = 1\n```\n\n"
        "| a |\n| - |\n| 1 |\n\n<Note>hi</Note>\n\n***\n\nend\n"
    )
    blocks = parse_blocks(text)

    assert blocks
    for previous, current in zip(blocks, blocks[1:]):
        assert previous.end <= current.start
    for block in blocks:
        assert text[block.start : block.end].strip()
