"""MDX-aware markdown parsing and chunk splitting.

The splitter never rewrites the source text: every chunk is an exact
half-open character slice ``text[start:end]`` of the original document, so the
stored offsets always point back into the file. Chunking only picks *break
points*; it does not strip, normalise or duplicate anything.

Strategy
--------
1. Parse the document into blocks: headings, fenced code, tables, block quotes,
   MDX components, lists, paragraphs, rules, frontmatter and JS export blocks.
2. Group blocks into sections using the heading hierarchy. Each chunk belongs to
   exactly one section and carries that section's heading path as *context*.
3. Greedily pack blocks of a section up to ``max_chars``. Oversized atomic
   blocks are split on line boundaries so a single 10 KB code fence does not
   become one chunk.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from .models import ChunkConfig

FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
HEADING_RE = re.compile(r"^ {0,3}(?P<hashes>#{1,6})[ \t]+(?P<title>.*?)(?:[ \t]+#+)?[ \t]*$")
LIST_RE = re.compile(r"^[ \t]{0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+")
EXPORT_RE = re.compile(
    r"^export[ \t]+(?:default[ \t]+|const[ \t]+|let[ \t]+|var[ \t]+|"
    r"function[ \t]+|async[ \t]+function[ \t]+|type[ \t]+|interface[ \t]+)"
)
MDX_OPEN_RE = re.compile(r"^<(?P<name>[A-Za-z][\w.:-]*)(?:[ \t/>]|$)")
RULE_RE = re.compile(
    r"^ {0,3}(?:\*[ \t]*){3,}$|^ {0,3}(?:-[ \t]*){3,}$|^ {0,3}(?:_[ \t]*){3,}$"
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
class RawChunk:
    """A chunk before it is bound to a document path.

    ``headings_with_levels`` keeps the original heading depth so a caller can
    rebuild the section path verbatim (``# A`` / ``## B`` / ``### C``).
    ``starts_with_heading`` is true when the chunk slice already begins with its
    own section heading, in which case that heading must not be duplicated when
    embedding the path into the chunk content.
    """

    start: int
    end: int
    start_line: int
    end_line: int
    headings: tuple[str, ...]
    context: str
    headings_with_levels: tuple[tuple[int, str], ...] = ()
    starts_with_heading: bool = False


@dataclass(slots=True)
class _Line:
    no: int
    start: int
    end: int
    text: str


@dataclass(slots=True)
class _Unit:
    headings: tuple[tuple[int, str], ...]
    blocks: list[Block] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Piece:
    start: int
    end: int
    hard_break: bool = False


def _lines(text: str) -> list[_Line]:
    """Split ``text`` into lines, keeping exact character offsets."""
    out: list[_Line] = []
    pos = 0
    for no, segment in enumerate(text.split("\n"), start=1):
        content = segment[:-1] if segment.endswith("\r") else segment
        out.append(_Line(no, pos, pos + len(content), content))
        pos += len(segment) + 1
    return out


def parse_blocks(text: str) -> list[Block]:
    """Parse ``text`` into blocks. Never mutates or copies the source text."""
    lines = _lines(text)
    total = len(lines)
    blocks: list[Block] = []
    index = 0

    if lines and lines[0].text.strip().lstrip("\ufeff") == "---":
        close = 1
        while close < total and lines[close].text.strip() not in {"---", "..."}:
            close += 1
        if close < total:
            blocks.append(Block("frontmatter", lines[0].start, lines[close].end))
            index = close + 1

    while index < total:
        line = lines[index]
        if line.start == 0 and line.text.startswith("\ufeff"):
            # A UTF-8 BOM is not part of the content: ignore it for parsing but
            # keep offsets anchored to the raw file (the BOM is simply skipped).
            line = _Line(line.no, line.start + 1, line.end, line.text[1:])
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
            blocks.append(
                Block(
                    "heading",
                    line.start,
                    line.end,
                    level=len(heading.group("hashes")),
                    title=heading.group("title").strip(),
                )
            )
            index += 1
            continue

        if EXPORT_RE.match(source):
            end = index
            balance = source.count("{") - source.count("}")
            while balance > 0 and end + 1 < total:
                following = lines[end + 1].text
                # Never let an unclosed export swallow a new markdown block.
                if HEADING_RE.match(following) or FENCE_RE.match(following):
                    break
                end += 1
                balance += following.count("{") - following.count("}")
            blocks.append(Block("export", line.start, lines[end].end))
            index = end + 1
            continue

        stripped = source.lstrip()
        if stripped.startswith("|"):
            end = index
            while end + 1 < total and lines[end + 1].text.lstrip().startswith("|"):
                end += 1
            blocks.append(Block("table", line.start, lines[end].end))
            index = end + 1
            continue

        if stripped.startswith(">"):
            end = index
            while end + 1 < total:
                following = lines[end + 1].text
                if following.lstrip().startswith(">"):
                    end += 1
                elif (
                    not following.strip()
                    and end + 2 < total
                    and lines[end + 2].text.lstrip().startswith(">")
                ):
                    end += 1
                else:
                    break
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
        end = index
        while end + 1 < total:
            following = lines[end + 1].text
            if not following.strip():
                break
            if (
                HEADING_RE.match(following)
                or FENCE_RE.match(following)
                or EXPORT_RE.match(following)
                or following.startswith("<")
            ):
                break
            end += 1
        blocks.append(Block(kind, line.start, lines[end].end))
        index = end + 1

    return blocks


def _read_fence(
    lines: list[_Line], index: int, match: re.Match[str], blocks: list[Block]
) -> int:
    """Read a fenced code block starting at ``index``; return the next index."""
    fence = match.group("fence")
    char = fence[0]
    info = match.group("info").strip()
    lang = info.split()[0].strip("{}.") if info else ""
    # CommonMark: a closing fence must be at least as long as the opening one,
    # otherwise ``` inside ````` would terminate the outer block.
    closing = re.compile(rf"^ {{0,3}}{re.escape(char)}{{{len(fence)},}}[ \t]*$")

    end = index + 1
    while end < len(lines) and not closing.match(lines[end].text):
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


def _find_mdx_close(lines: list[_Line], index: int, name: str) -> int | None:
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

    open_re = re.compile(rf"<{re.escape(name)}(?:[ \t/>]|$)")
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
        if open_re.match(trimmed) and not trimmed.endswith("/>"):
            depth += 1
        if close_tag in trimmed:
            depth -= 1
            if depth <= 0:
                return cursor
        cursor += 1

    return None


def build_units(blocks: list[Block]) -> list[_Unit]:
    """Group blocks into heading-scoped units."""
    units: list[_Unit] = []
    stack: list[tuple[int, str]] = []
    current: _Unit | None = None

    for block in blocks:
        if block.kind == "heading":
            while stack and stack[-1][0] >= block.level:
                stack.pop()
            stack.append((block.level, block.title))
            current = _Unit(tuple(stack), [block])
            units.append(current)
            continue
        if current is None:
            current = _Unit(())
            units.append(current)
        current.blocks.append(block)

    return units


def _split_oversized(block: Block, text: str, max_chars: int) -> list[tuple[int, int]]:
    """Split an oversized atomic block on line boundaries.

    Break points prefer, in order: the start of a nested element (so oversized
    ``<Tabs>``/``<Steps>`` blocks break between their children instead of inside
    one), then a blank line, then an arbitrary line.
    """
    lines = _lines(text[block.start : block.end])
    base = block.start
    spans: list[tuple[int, int]] = []
    start = 0

    def size(first: int, last: int) -> int:
        return base + lines[last].end - (base + lines[first].start)

    while start < len(lines):
        end = start
        blank_break: int | None = None
        element_break: int | None = None
        while end + 1 < len(lines):
            candidate = base + lines[end + 1].end
            if candidate - (base + lines[start].start) > max_chars:
                break
            end += 1
            stripped = lines[end].text.strip()
            if not stripped:
                blank_break = end
            elif stripped.startswith("<") and not stripped.startswith("</"):
                element_break = end

        if blank_break is not None and blank_break > start and size(start, blank_break) >= max_chars * 0.4:
            end = blank_break
        if (
            element_break is not None
            and element_break - 1 > start
            and size(start, element_break - 1) >= max_chars * 0.4
        ):
            end = element_break - 1

        spans.append((base + lines[start].start, base + lines[end].end))
        start = end + 1

    return spans


def _unit_pieces(unit: _Unit, text: str, config: ChunkConfig) -> list[_Piece]:
    """Flatten a section into packable pieces.

    Blocks of a skipped kind (frontmatter, ``export`` helpers) become a *hard
    break*: the next piece starts a new chunk, so those blocks never leak into a
    chunk as part of the gap between two kept blocks.
    """
    pieces: list[_Piece] = []
    hard_break = False
    for block in unit.blocks:
        snippet = text[block.start : block.end].lstrip()
        if block.kind in config.skip_kinds or snippet.startswith(config.skip_prefixes):
            hard_break = True
            continue
        spans = (
            [(block.start, block.end)]
            if block.end - block.start <= config.max_chars
            else _split_oversized(block, text, config.max_chars)
        )
        for start, end in spans:
            pieces.append(_Piece(start, end, hard_break))
            hard_break = False
    return pieces


def _emit_unit(unit: _Unit, text: str, config: ChunkConfig) -> list[tuple[int, int]]:
    """Turn one section into chunk offset ranges."""
    pieces = _unit_pieces(unit, text, config)
    if not pieces:
        return []

    heading = None
    if unit.blocks and unit.blocks[0].kind == "heading":
        heading = (pieces[0].start, pieces[0].end)

    ranges: list[list[int]] = []
    for piece in pieces:
        fits = ranges and not piece.hard_break and piece.end - ranges[-1][0] <= config.max_chars
        # A section heading always travels with the first piece of its body,
        # even when that body is a single oversized block.
        heading_only = (
            not piece.hard_break
            and bool(ranges)
            and heading is not None
            and ranges[-1][0] == heading[0]
            and ranges[-1][1] <= heading[1]
        )
        if fits or heading_only:
            ranges[-1][1] = piece.end
        else:
            ranges.append([piece.start, piece.end])

    if ranges and heading is not None and ranges[0] == list(heading):
        # A heading with no body (or followed by a skipped block) is not a chunk.
        ranges.pop(0)

    return [(start, end) for start, end in ranges]


def _line_number(line_starts: list[int], offset: int) -> int:
    return bisect.bisect_right(line_starts, offset)


def split_text(text: str, config: ChunkConfig | None = None) -> list[RawChunk]:
    """Split ``text`` into chunks addressed by character offsets."""
    settings = config or ChunkConfig()
    if not text.strip():
        return []

    line_starts = [0]
    for position, char in enumerate(text):
        if char == "\n":
            line_starts.append(position + 1)

    chunks: list[RawChunk] = []
    for unit in build_units(parse_blocks(text)):
        context = " > ".join(title for _, title in unit.headings)
        first_block = unit.blocks[0] if unit.blocks else None
        for start, end in _emit_unit(unit, text, settings):
            if not text[start:end].strip():  # pragma: no cover - blocks are never blank
                continue
            chunks.append(
                RawChunk(
                    start=start,
                    end=end,
                    start_line=_line_number(line_starts, start),
                    end_line=_line_number(line_starts, max(start, end - 1)),
                    headings=tuple(title for _, title in unit.headings),
                    context=context,
                    headings_with_levels=unit.headings,
                    starts_with_heading=first_block is not None
                    and first_block.kind == "heading"
                    and first_block.start == start,
                )
            )
    return chunks
