"""Markdown/MDX block parsing.

Turns a document into a flat list of :class:`Block` objects addressed by
character offsets: headings, fenced code, tables, block quotes, MDX components,
lists, paragraphs, rules, frontmatter and inline JS exports.

Parsing never rewrites the source text, so every block is an exact slice of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


HEADING_RE = re.compile(r"^ {0,3}(?P<hashes>#{1,6})[ \t]+(?P<title>.*?)(?:[ \t]+#+)?[ \t]*$")


LIST_RE = re.compile(r"^[ \t]{0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+")


MDX_OPEN_RE = re.compile(r"^<(?P<name>[A-Za-z][\w.:-]*)(?:[ \t/>]|$)")


RULE_RE = re.compile(
    r"^ {0,3}(?:\*[ \t]*){3,}$|^ {0,3}(?:-[ \t]*){3,}$|^ {0,3}(?:_[ \t]*){3,}$"
)
SETEXT_RE = re.compile(r"^ {0,3}(?P<marks>=+|-+)[ \t]*$")
MATH_RE = re.compile(r"^[ \t]*\$\$")
CONTAINER_RE = re.compile(r"^[ \t]*:::[ \t]*(?P<name>[A-Za-z][\w-]*)")
FOOTNOTE_RE = re.compile(r"^\[\^[^\]]+\]:")
IMPORT_RE = re.compile(r"^import[ \t]+")
MDX_COMMENT_RE = re.compile(r"^\{/\*")


EXPORT_RE = re.compile(
    r"^export[ \t]+(?:\{[^}]*\}|\*[ \t]*(?:from|as)\b|default\b|const\b|"
    r"let\b|var\b|function\b|async[ \t]+function\b|class\b|type\b|"
    r"interface\b|enum\b)"
)
HTML_COMMENT_RE = re.compile(r"^[ \t]*<!--")


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

        if MATH_RE.match(source):
            end = _read_math(lines, index, blocks)
            if end is not None:
                index = end
                continue

        if CONTAINER_RE.match(source):
            end = _read_container(lines, index)
            if end is not None:
                blocks.append(Block("container", line.start, lines[end].end))
                index = end + 1
                continue

        if FOOTNOTE_RE.match(source):
            end = _end_of_footnote(lines, index)
            blocks.append(Block("footnote", line.start, lines[end].end))
            index = end + 1
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

        if IMPORT_RE.match(source):
            end = _end_of_import(lines, index)
            blocks.append(Block("import", line.start, lines[end].end))
            index = end + 1
            continue

        if HTML_COMMENT_RE.match(source):
            end = _end_of_html_comment(lines, index)
            if end is not None:
                blocks.append(Block("comment", line.start, lines[end].end))
                index = end + 1
                continue

        if MDX_COMMENT_RE.match(source):
            end = _end_of_mdx_comment(lines, index)
            blocks.append(Block("comment", line.start, lines[end].end))
            index = end + 1
            continue

        if _is_table_start(lines, index):
            end = _end_of_table(lines, index)
            blocks.append(Block("table", line.start, lines[end].end))
            index = end + 1
            continue

        stripped = source.lstrip()

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


def _end_of_import(lines: list[Line], index: int) -> int:
    """Last line of an ESM import statement.

    A statement without ``{`` / ``(`` and without a semicolon is treated as a
    single line. Extending it until a blank line (the old behaviour) swallowed
    the following paragraph, which then disappeared with the skipped block.
    """
    first = lines[index].text
    if ";" in first or ("{" not in first and "(" not in first):
        return index

    balance = (
        first.count("{") - first.count("}") + first.count("(") - first.count(")")
    )
    end = index
    while balance > 0 and end + 1 < len(lines):
        following = lines[end + 1].text
        if (
            not following.strip()
            or HEADING_RE.match(following)
            or FENCE_RE.match(following)
        ):
            break
        end += 1
        balance += (
            following.count("{") - following.count("}")
            + following.count("(") - following.count(")")
        )
    return end


def _end_of_html_comment(lines: list[Line], index: int) -> int | None:
    """Last line of an HTML comment, or ``None`` when it is unclosed."""
    for end in range(index, len(lines)):
        if "-->" in lines[end].text:
            return end
    return None


def _end_of_mdx_comment(lines: list[Line], index: int) -> int:
    """Last line of an MDX comment (``{/* ... */}``)."""
    end = index
    if "*/}" in lines[index].text:
        return end
    limit = min(len(lines) - 1, index + 100)
    while end < limit:
        end += 1
        if "*/}" in lines[end].text:
            break
    return end


def _is_table_start(lines: list[Line], index: int) -> bool:
    """GFM table: a header row with a pipe followed by an alignment row."""
    if index + 1 >= len(lines) or "|" not in lines[index].text:
        return False
    separator = lines[index + 1].text.strip()
    return (
        bool(separator)
        and "-" in separator
        and separator.count("|") >= 1
        and all(char in "|:- \t" for char in separator)
    )


def _end_of_table(lines: list[Line], index: int) -> int:
    """Last row of a table; GFM rows need a pipe but not a leading one."""
    end = index
    while end + 1 < len(lines):
        following = lines[end + 1].text
        if (
            not following.strip()
            or "|" not in following
            or HEADING_RE.match(following)
            or FENCE_RE.match(following)
        ):
            break
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
            or RULE_RE.match(following)
            or MATH_RE.match(following)
            or CONTAINER_RE.match(following)
            or FOOTNOTE_RE.match(following)
            or HTML_COMMENT_RE.match(following)
            or _is_table_start(lines, end + 1)
            or following.startswith("<")
            or _setext_level(following) is not None
        ):
            break
        end += 1
    return end


def _indent_width(line: str) -> int:
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip(" "))


def _is_closing_fence(line: str, char: str, minimum: int, max_indent: int) -> bool:
    """Whether ``line`` closes a fence opened with ``minimum`` ``char``s.

    A closing fence may be indented at most three columns past the opening one;
    this is what lets list-item fences work without letting an indented code
    sample inside a fence terminate it early.
    """
    if _indent_width(line) > max_indent:
        return False
    body = line.lstrip(" \t").rstrip(" \t")
    return len(body) >= minimum and set(body) == {char}


def _setext_level(text: str) -> int | None:
    """Heading level of a Setext underline (``===`` -> 1, ``---`` -> 2)."""
    match = SETEXT_RE.match(text)
    if match is None:
        return None
    return 1 if match.group("marks")[0] == "=" else 2


def _read_math(lines: list[Line], index: int, blocks: list[Block]) -> int | None:
    """Read a ``$$`` display-math block; return the next index or ``None``.

    Treating display math as one atomic block keeps ``#`` inside an equation out
    of the heading tree. An unclosed ``$$`` falls back to normal paragraph
    parsing so it cannot swallow the rest of the document.
    """
    first = lines[index].text.strip()
    if first.endswith("$$") and len(first) > 4:
        blocks.append(Block("math", lines[index].start, lines[index].end))
        return index + 1

    for end in range(index + 1, len(lines)):
        if "$$" in lines[end].text:
            blocks.append(Block("math", lines[index].start, lines[end].end))
            return end + 1
    return None


def _read_container(lines: list[Line], index: int) -> int | None:
    """Read a ``:::name ... :::`` container; ``None`` when it is unclosed."""
    for end in range(index + 1, len(lines)):
        if lines[end].text.strip() == ":::":
            return end
    return None


def _end_of_footnote(lines: list[Line], index: int) -> int:
    """Last line of a footnote definition (continuation lines are indented)."""
    end = index
    while end + 1 < len(lines):
        following = lines[end + 1].text
        if not following.strip():
            break
        if not following.startswith(("    ", "\t")):
            break
        end += 1
    return end


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

    max_indent = _indent_width(match.group("indent")) + 3
    end = index + 1
    while end < len(lines) and not _is_closing_fence(
        lines[end].text, char, len(fence), max_indent
    ):
        end += 1
    if end < len(lines):
        blocks.append(Block("code", lines[index].start, lines[end].end, lang=lang))
        return end + 1
    blocks.append(Block("code", lines[index].start, lines[-1].end, lang=lang))
    return len(lines)


INNER_FENCE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>.*)$"
)


def _closes_fence(line: str, fence: str, max_indent: int) -> bool:
    match = INNER_FENCE_RE.match(line)
    if match is None:
        return False
    candidate = match.group("fence")
    return (
        candidate[0] == fence[0]
        and len(candidate) >= len(fence)
        and _indent_width(match.group("indent")) <= max_indent
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

    open_re = re.compile(rf"<{re.escape(name)}(?=[ \t/>]|$)")
    close_re = re.compile(rf"</{re.escape(name)}(?=[ \t>]|$)")
    self_close_re = re.compile(rf"<{re.escape(name)}\b[^>]*/>")
    depth = 1
    fence: str | None = None
    fence_indent = 0
    cursor = index + 1

    while cursor < len(lines):
        current = lines[cursor].text

        if fence is not None:
            if _closes_fence(current, fence, fence_indent + 3):
                fence = None
            cursor += 1
            continue

        opening = INNER_FENCE_RE.match(current)
        if opening is not None:
            fence = opening.group("fence")
            fence_indent = _indent_width(opening.group("indent"))
            cursor += 1
            continue

        # Count every tag on the line: nested components often share a line
        # (``<TabItem><Tabs>``), so only matching the line prefix is not enough.
        opens = len(open_re.findall(current))
        self_closes = len(self_close_re.findall(current))
        closes = len(close_re.findall(current))
        depth += opens - self_closes - closes
        if depth <= 0:
            return cursor
        cursor += 1

    return None


__all__ = ["Block", "Line", "parse_blocks", "split_lines"]
