"""基于固定种子的随机文档测试：切分不变量必须永远成立。

不比对具体输出，只校验结构性约束（切片精确、有序、不重叠、行边界、行号），
因此新增解析分支时不会频繁失效，但切分逻辑出问题会立刻暴露。
"""

from __future__ import annotations

import random

import pytest

from langchain_md_chunker import ChunkConfig, Chunker, parse_blocks

PIECES = [
    "# Title",
    "## Section",
    "### Deep",
    "Plain paragraph text with words.",
    "Another paragraph with `code` and [link](/x).",
    "- one\n- two",
    "1. first\n2. second",
    "> quoted\n> second line",
    "***",
    "| a | b |\n| - | - |\n| 1 | 2 |",
    "```python\nprint(1)\n```",
    "````md\n```python\nprint(2)\n```\n````",
    "~~~bash\necho hi\n~~~",
    "```python\nunclosed fence",
    '<Note icon="x">\n  note body\n</Note>',
    '<Tabs>\n  <Tab title="a">\n\n    body a\n\n  </Tab>\n</Tabs>',
    '<Accordion title="o">\n  <Accordion title="i">\n    inner\n  </Accordion>\n</Accordion>',
    "<br>",
    "export const X = ({active}) => {\n  return active;\n};",
    "export const Broken = () => {\n  const a = 1;",
    "---\ntitle: front\n---",
    "---",
    '<div className="source-links">\n  <Callout icon="edit">\n    [Edit](x)\n  </Callout>\n</div>',
    "> ## Documentation Index\n> Fetch index.",
    "\u4e2d\u6587\u6bb5\u843d\uff0c\u542b emoji \U0001F680 \u4e0e e\u0301\u3002",
    "    indented line",
    '<Steps>\n  <Step title="s">\n\n    step body\n\n  </Step>\n</Steps>',
]


def make_doc(rng: random.Random) -> str:
    text = "\n\n".join(rng.choice(PIECES) for _ in range(rng.randint(1, 12)))
    if rng.random() < 0.3:
        text += "\n"
    if rng.random() < 0.2:
        text = "---\ntitle: fm\n---\n\n" + text
    if rng.random() < 0.1:
        text = "\ufeff" + text
    if rng.random() < 0.2:
        text = text.replace("\n", "\r\n")
    return text


def check(text: str, config: ChunkConfig) -> None:
    blocks = parse_blocks(text)
    usable = [
        block
        for block in blocks
        if block.kind != "heading"
        and block.kind not in config.skip_kinds
        and not text[block.start : block.end].lstrip().startswith(config.skip_prefixes)
    ]
    chunks = Chunker(config).split_text(text, doc="fuzz.md")

    if usable:
        assert chunks, "有可用内容却没有产出 chunk"

    previous_end = 0
    for chunk in chunks:
        assert 0 <= chunk.start < chunk.end <= len(text)
        assert text[chunk.start : chunk.end] == chunk.text
        assert chunk.chars == len(chunk.text)
        assert chunk.text.strip()
        assert chunk.start >= previous_end, "chunk 重叠或乱序"
        previous_end = chunk.end

        if chunk.start != 0:
            previous = text[chunk.start - 1]
            # 唯一的例外：文件开头有 BOM，切分从 BOM 之后开始
            assert previous == "\n" or (chunk.start == 1 and previous == "\ufeff"), "起点不在行边界"
        if chunk.end != len(text):
            assert text[chunk.end] in "\r\n", "终点不在行边界"
        assert chunk.start_line == text[: chunk.start].count("\n") + 1
        assert chunk.end_line == text[: chunk.end - 1].count("\n") + 1


@pytest.mark.parametrize("max_chars", [1, 30, 400, 1500])
def test_random_documents_keep_invariants(max_chars: int) -> None:
    rng = random.Random(20261020 + max_chars)
    for _ in range(60):
        check(make_doc(rng), ChunkConfig(max_chars=max_chars))


@pytest.mark.parametrize("max_chars", [30, 400])
def test_include_headings_only_prepends_heading_lines(max_chars: int) -> None:
    rng = random.Random(7 + max_chars)
    config = ChunkConfig(max_chars=max_chars, include_headings=True)
    for _ in range(40):
        text = make_doc(rng)
        for chunk in Chunker(config).split_text(text):
            assert chunk.content.endswith(chunk.text)
            prefix = chunk.content[: len(chunk.content) - len(chunk.text)]
            if prefix:
                assert prefix.endswith("\n\n")
                for line in prefix.rstrip("\n").split("\n"):
                    assert line.startswith("#")
