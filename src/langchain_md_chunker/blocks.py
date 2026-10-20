"""Markdown/MDX block parsing.

Turns a document into a flat list of :class:`Block` objects addressed by
character offsets: headings, fenced code, tables, block quotes, MDX components,
lists, paragraphs, rules, frontmatter and inline JS exports.

Parsing never rewrites the source text, so every block is an exact slice of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


HEADING_RE = re.compile(r"^ {0,3}(?P<hashes>#{1,6})[ \t]+(?P<title>.*?)(?:[ \t]+#+)?[ \t]*$")


LIST_RE = re.compile(r"^[ \t]{0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+")


MDX_OPEN_RE = re.compile(r"^<(?P<name>[A-Za-z][\w.:-]*)(?:[ \t/>]|$)")


RULE_RE = re.compile(
    r"^ {0,3}(?:\*[ \t]*){3,}$|^ {0,3}(?:-[ \t]*){3,}$|^ {0,3}(?:_[ \t]*){3,}$"
)
SETEXT_RE = re.compile(r"^ {0,3}(?P<marks>=+|-+)[ \t]*$")


EXPORT_RE = re.compile(
    r"^export[ \t]+(?:default[ \t]+|const[ \t]+|let[ \t]+|var[ \t]+|"
    r"function[ \t]+|async[ \t]+function[ \t]+|type[ \t]+|interface[ \t]+)"
)


@dataclass(frozen=True, slots=True)
class Block:
    """A parsed block of the source document, addressed by character offsets."""

    kind: str
    start: int
    end: int
    level: int = 0
    title: str = ""
    lang: str = ""


@dataclass(frozen=True, slots=True)
class Line:
    start: int
    end: int
    text: str


def split_lines(text: str) -> list[Line]:
    """Split ``text`` into lines, keeping exact character offsets.

    A trailing newline yields one extra empty line at ``len(text)``; such lines
    are blank and never produce blocks.
    """
    out: list[Line] = []
    pos = 0
    for segment in text.split("\n"):
        content = segment.removesuffix("\r")
        out.append(Line(pos, pos + len(content), content))
        pos += len(segment) + 1
    return out


def parse_blocks(text: str) -> list[Block]:
    """Parse ``text`` into blocks. Never mutates or copies the source text."""
    lines = split_lines(text)
    total = len(lines)
    blocks: list[Block] = []
    index = 0

    frontmatter_end = _end_of_frontmatter(lines)
    if frontmatter_end is not None:
        blocks.append(Block("frontmatter", lines[0].start, lines[frontmatter_end].end))
        index = frontmatter_end + 1

    while index < total:
        line = lines[index]
        if line.start == 0 and line.text.startswith("\ufeff"):
            # A UTF-8 BOM is not part of the content: ignore it for parsing but
            # keep offsets anchored to the raw file (the BOM is simply skipped).
            line = Line(line.start + 1, line.end, line.text[1:])
        source = line.text

        if not source.strip():
            index += 1
            continue

        fence = FENCE_RE.match(source)
        if fence:
            index = _read_fence(lines, index, fence, blocks)
            continue

        heading = HEADING_RE.match(source)
        if heading:
            blocks.append(_heading_block(line, heading))
            index += 1
            continue

        if EXPORT_RE.match(source):
            end = _end_of_export(lines, index)
            blocks.append(Block("export", line.start, lines[end].end))
            index = end + 1
            continue

        stripped = source.lstrip()
        if stripped.startswith("|"):
            end = _end_of_table(lines, index)
            blocks.append(Block("table", line.start, lines[end].end))
            index = end + 1
            continue

        if stripped.startswith(">"):
            end = _end_of_quote(lines, index)
            blocks.append(Block("quote", line.start, lines[end].end))
            index = end + 1
            continue

        if RULE_RE.match(source):
            blocks.append(Block("rule", line.start, line.end))
            index += 1
            continue

        mdx = MDX_OPEN_RE.match(source)
        if mdx:
            close = _find_mdx_close(lines, index, mdx.group("name"))
            if close is not None:
                blocks.append(Block("mdx", line.start, lines[close].end))
                index = close + 1
                continue

        kind = "list" if LIST_RE.match(source) else "para"
        end = _end_of_paragraph(lines, index)
        if kind == "para" and end + 1 < total:
            level = _setext_level(lines[end + 1].text)
            if level is not None:
                title = " ".join(
                    lines[position].text.strip() for position in range(index, end + 1)
                ).strip()
                blocks.append(
                    Block("heading", line.start, lines[end + 1].end, level=level, title=title)
                )
                index = end + 2
                continue
        blocks.append(Block(kind, line.start, lines[end].end))
        index = end + 1

    return blocks


def _end_of_frontmatter(lines: list[Line]) -> int | None:
    """Return the closing ``---`` line index, or ``None`` when there is none."""
    if not lines or lines[0].text.strip().lstrip("\ufeff") != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].text.strip() in {"---", "..."}:
            return index
    return None


def _heading_block(line: Line, match: re.Match[str]) -> Block:
    return Block(
        "heading",
        line.start,
        line.end,
        level=len(match.group("hashes")),
        title=match.group("title").strip(),
    )


def _end_of_export(lines: list[Line], index: int) -> int:
    """Last line of an ``export`` block, tracked by brace balance.

    LangChain docs embed multi-kilobyte JSX components in a single export; they
    contain blank lines, so brace balance (not blank lines) decides the end. A
    heading or fence always terminates the block early.
    """
    end = index
    balance = lines[index].text.count("{") - lines[index].text.count("}")
    while balance > 0 and end + 1 < len(lines):
        following = lines[end + 1].text
        if HEADING_RE.match(following) or FENCE_RE.match(following):
            break
        end += 1
        balance += following.count("{") - following.count("}")
    return end


def _end_of_table(lines: list[Line], index: int) -> int:
    end = index
    while end + 1 < len(lines) and lines[end + 1].text.lstrip().startswith("|"):
        end += 1
    return end


def _end_of_quote(lines: list[Line], index: int) -> int:
    """Last line of a block quote; a blank line keeps the quote open."""
    end = index
    while end + 1 < len(lines):
        following = lines[end + 1].text
        if following.lstrip().startswith(">") or (
            not following.strip()
            and end + 2 < len(lines)
            and lines[end + 2].text.lstrip().startswith(">")
        ):
            end += 1
        else:
            break
    return end


def _end_of_paragraph(lines: list[Line], index: int) -> int:
    """Last line of a paragraph/list; stops at blank lines and new blocks."""
    end = index
    while end + 1 < len(lines):
        following = lines[end + 1].text
        if not following.strip():
            break
        if (
            HEADING_RE.match(following)
            or FENCE_RE.match(following)
            or EXPORT_RE.match(following)
            or following.startswith("<")
            or _setext_level(following) is not None
        ):
            break
        end += 1
    return end


def _is_closing_fence(line: str, char: str, minimum: int) -> bool:
    """Whether ``line`` closes a fence opened with ``minimum`` ``char``s."""
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    body = stripped.rstrip(" \t")
    return len(body) >= minimum and set(body) == {char}


def _setext_level(text: str) -> int | None:
    """Heading level of a Setext underline (``===`` -> 1, ``---`` -> 2)."""
    match = SETEXT_RE.match(text)
    if match is None:
        return None
    return 1 if match.group("marks")[0] == "=" else 2


def _read_fence(
    lines: list[Line], index: int, match: re.Match[str], blocks: list[Block]
) -> int:
    """Read a fenced code block starting at ``index``; return the next index.

    CommonMark: a closing fence must be at least as long as the opening one,
    otherwise ``` inside ````` would terminate the outer block.
    """
    fence = match.group("fence")
    char = fence[0]
    info = match.group("info").strip()
    lang = info.split()[0].strip("{}.") if info else ""

    end = index + 1
    while end < len(lines) and not _is_closing_fence(lines[end].text, char, len(fence)):
        end += 1
    if end < len(lines):
        blocks.append(Block("code", lines[index].start, lines[end].end, lang=lang))
        return end + 1
    blocks.append(Block("code", lines[index].start, lines[-1].end, lang=lang))
    return len(lines)


INNER_FENCE_RE = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>.*)$")


def _closes_fence(line: str, fence: str) -> bool:
    match = INNER_FENCE_RE.match(line)
    if match is None:
        return False
    candidate = match.group("fence")
    return (
        candidate[0] == fence[0]
        and len(candidate) >= len(fence)
        and not match.group("info").strip()
    )


def _find_mdx_close(lines: list[Line], index: int, name: str) -> int | None:
    """Locate the closing tag of an MDX component, or ``None`` if it is not a block.

    Fenced code blocks are skipped while counting nesting depth, otherwise a code
    sample containing ``<Tabs>`` would corrupt the depth. A component without a
    closing tag (stray inline HTML) falls back to being parsed as a paragraph, so
    a broken tag can never swallow the rest of the document.
    """
    source = lines[index].text
    close_tag = f"</{name}"
    if source.rstrip().endswith("/>") or close_tag in source:
        return index

    open_prefix = f"<{name}"
    depth = 1
    fence: str | None = None
    cursor = index + 1

    while cursor < len(lines):
        current = lines[cursor].text

        if fence is not None:
            if _closes_fence(current, fence):
                fence = None
            cursor += 1
            continue

        opening = INNER_FENCE_RE.match(current)
        if opening is not None:
            fence = opening.group("fence")
            cursor += 1
            continue

        # Nested components are usually indented, so match the tag after trimming.
        trimmed = current.strip()
        if _opens_tag(trimmed, open_prefix) and not trimmed.endswith("/>"):
            depth += 1
        if close_tag in trimmed:
            depth -= 1
            if depth <= 0:
                return cursor
        cursor += 1

    return None


def _opens_tag(trimmed: str, prefix: str) -> bool:
    """Whether a trimmed line opens the tag named by ``prefix`` (``<Tabs``)."""
    if not trimmed.startswith(prefix):
        return False
    rest = trimmed[len(prefix) :]
    return rest[:1] in {"", " ", "\t", "/", ">"}

__all__ = ["Block", "Line", "parse_blocks", "split_lines"]
