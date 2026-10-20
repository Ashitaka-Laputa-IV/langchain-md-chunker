"""解析层边界：围栏嵌套、围栏内伪标题、表格、MDX、分隔线。"""

from __future__ import annotations

import itertools

from langchain_md_chunker import Chunker
from langchain_md_chunker.blocks import parse_blocks


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


def test_rule_after_paragraph_is_not_swallowed() -> None:
    text = "para\n***\n\nafter\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["para", "rule", "para"]


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


def test_utf8_bom_is_ignored_for_parsing() -> None:
    text = "\ufeff# Title\n\nbody\n"
    blocks = parse_blocks(text)

    assert blocks[0].kind == "heading"
    assert blocks[0].title == "Title"
    assert blocks[0].start == 1, "BOM 不应计入块起点"
    assert text[blocks[0].start : blocks[0].end] == "# Title"


def test_bom_with_frontmatter() -> None:
    text = "\ufeff---\ntitle: x\n---\n\n# T\n\nbody\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks][:2] == ["frontmatter", "heading"]


def test_export_block_stops_at_heading() -> None:
    text = "# T\n\nexport const x = 1;\n# Next\n\nbody text\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["heading", "export", "heading", "para"]
    assert text[blocks[2].start : blocks[2].end] == "# Next"


def test_export_block_continues_while_braces_are_open() -> None:
    text = (
        "export const X = () => {\n  const a = 1;\n\n  return a;\n};\n\n# T\n\nbody\n"
    )
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["export", "heading", "para"]
    assert "return a;" in text[blocks[0].start : blocks[0].end]
    assert text[blocks[1].start : blocks[1].end] == "# T"


def test_unclosed_export_stops_at_heading() -> None:
    text = "export const Broken = () => {\n  const a = 1;\n# Heading\n\nbody\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["export", "heading", "para"]
    assert text[blocks[1].start : blocks[1].end] == "# Heading"


def test_export_at_end_of_file() -> None:
    assert [block.kind for block in parse_blocks("export const x = 1;")] == ["export"]


def test_tag_inside_code_fence_does_not_break_component() -> None:
    text = (
        '<Tabs>\n  <Tab title="a">\n    ```md\n    <Tabs>\n    ```\n  </Tab>\n</Tabs>\n'
        "\n# After\n\ntail\n"
    )
    blocks = parse_blocks(text)

    assert blocks[0].kind == "mdx"
    assert text[blocks[0].start : blocks[0].end].endswith("</Tabs>")
    assert [block.kind for block in blocks[1:]] == ["heading", "para"]


def test_component_may_contain_headings() -> None:
    text = '<Accordion title="a">\n  ### Sub heading\n\n  body\n</Accordion>\n\nafter\n'
    blocks = parse_blocks(text)

    assert blocks[0].kind == "mdx"
    assert text[blocks[0].start : blocks[0].end].endswith("</Accordion>")
    assert text[blocks[1].start : blocks[1].end] == "after"


def test_long_component_is_still_one_block() -> None:
    inner = "\n".join(f"    line {index}" for index in range(500))
    text = f'<Tabs>\n  <Tab title="big">\n{inner}\n  </Tab>\n</Tabs>\n\n# After\n\ntail\n'
    blocks = parse_blocks(text)

    assert blocks[0].kind == "mdx"
    assert text[blocks[0].start : blocks[0].end].endswith("</Tabs>")
    assert [block.kind for block in blocks[1:]] == ["heading", "para"]


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
    for previous, current in itertools.pairwise(blocks):
        assert previous.end <= current.start
    for block in blocks:
        assert text[block.start : block.end].strip()

def test_setext_headings() -> None:
    text = "Title\n=====\n\nbody\n\nSub\n---\n\nmore\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["heading", "para", "heading", "para"]
    assert [(block.level, block.title) for block in blocks if block.kind == "heading"] == [
        (1, "Title"),
        (2, "Sub"),
    ]
    assert text[blocks[0].start : blocks[0].end] == "Title\n====="


def test_setext_underline_after_blank_line_is_a_rule() -> None:
    text = "para\n\n---\n\nnext\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["para", "rule", "para"]

def test_mdx_import_is_skipped() -> None:
    text = "import Tabs from '@theme/Tabs';\n\n# T\n\nbody\n"
    chunks = Chunker().split_text(text)

    assert len(chunks) == 1
    assert "import" not in chunks[0].text


def test_multiline_import_is_one_block() -> None:
    text = "import {\n  A,\n  B,\n} from './x';\n\n# T\n\nbody\n"
    blocks = parse_blocks(text)

    assert blocks[0].kind == "import"
    assert text[blocks[0].start : blocks[0].end].startswith("import {")
    assert text[blocks[0].start : blocks[0].end].endswith("from './x';")
    assert "import" not in Chunker().split_text(text)[0].text


def test_mdx_comment_is_skipped() -> None:
    text = "{/*\n  hidden note\n*/}\n\n# T\n\nbody\n"
    chunks = Chunker().split_text(text)

    assert len(chunks) == 1
    assert "hidden note" not in chunks[0].text


def test_import_without_semicolon_at_eof() -> None:
    assert [block.kind for block in parse_blocks("import x")] == ["import"]


def test_import_without_semicolon_stops_at_blank_line() -> None:
    blocks = parse_blocks("import x\n\n# T\n")

    assert [block.kind for block in blocks] == ["import", "heading"]


def test_single_line_mdx_comment_is_skipped() -> None:
    text = "{/* hidden */}\n\n# T\n\nbody\n"

    chunks = Chunker().split_text(text)

    assert len(chunks) == 1
    assert "hidden" not in chunks[0].text


def test_unclosed_mdx_comment_runs_to_eof() -> None:
    blocks = parse_blocks("{/* hidden")

    assert [block.kind for block in blocks] == ["comment"]
    assert blocks[0].end == len("{/* hidden")


def test_import_inside_fence_stays_code() -> None:
    text = "```python\nimport os\n```\n"
    blocks = parse_blocks(text)

    assert [block.kind for block in blocks] == ["code"]

