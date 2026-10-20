"""Section grouping and chunk assembly.

Consumes the blocks produced by :mod:`langchain_md_chunker.blocks`, groups them by
heading hierarchy, and packs each section into offset ranges <= ``max_chars``.
Chunks are *ranges only*: the source text is never duplicated or rewritten.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

from .blocks import Block, parse_blocks, split_lines
from .config import ChunkConfig


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
    context: str
    headings_with_levels: tuple[tuple[int, str], ...] = ()
    starts_with_heading: bool = False
    kind: str = "text"
    lang: str = ""

    @property
    def headings(self) -> tuple[str, ...]:
        """Heading titles from outermost to innermost."""
        return tuple(title for _, title in self.headings_with_levels)


@dataclass(slots=True)
class _Unit:
    headings: tuple[tuple[int, str], ...]
    blocks: list[Block] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Piece:
    start: int
    end: int
    hard_break: bool = False
    kind: str = "para"
    lang: str = ""


@dataclass(slots=True)
class _Range:
    start: int
    end: int
    pieces: list[_Piece]


def _build_units(blocks: list[Block]) -> list[_Unit]:
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


#: Block kinds whose over-long single line may be split inside the line.
_TEXT_KINDS = frozenset({"para", "list", "quote"})
_SENTENCE_ENDS = "。！？.!?…"
_CLAUSE_ENDS = "，,；;、：:"


def _last_break(window: str, marks: str) -> int:
    return max(window.rfind(mark) for mark in marks)


def _split_line(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Split one over-long line, preferring sentence end, then clause, then hard cut."""
    spans: list[tuple[int, int]] = []
    while end - start > max_chars:
        window = text[start : start + max_chars]
        cut = _last_break(window, _SENTENCE_ENDS)
        if cut < max(1, max_chars // 3):
            cut = _last_break(window, _CLAUSE_ENDS)
        if cut < max(1, max_chars // 3):
            cut = max_chars - 1
        cut += 1
        spans.append((start, start + cut))
        start += cut
        while start < end and text[start].isspace():
            start += 1
    if start < end:
        spans.append((start, end))
    return spans


def _split_oversized(block: Block, text: str, max_chars: int) -> list[tuple[int, int]]:
    """Split an oversized atomic block on line boundaries.

    Break points prefer, in order: the start of a nested element (so oversized
    ``<Tabs>``/``<Steps>`` blocks break between their children instead of inside
    one), then a blank line, then an arbitrary line.
    """
    lines = split_lines(text[block.start : block.end])
    base = block.start
    spans: list[tuple[int, int]] = []
    start = 0

    def size(first: int, last: int) -> int:
        return base + lines[last].end - (base + lines[first].start)

    while start < len(lines):
        line = lines[start]
        line_start = base + line.start
        line_end = base + line.end
        if block.kind in _TEXT_KINDS and line_end - line_start > max_chars:
            spans.extend(_split_line(text, line_start, line_end, max_chars))
            start += 1
            continue

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

        if (
            blank_break is not None
            and blank_break > start
            and size(start, blank_break) >= max_chars * 0.4
        ):
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
            pieces.append(_Piece(start, end, hard_break, block.kind, block.lang))
            hard_break = False
    return pieces


def _emit_unit(unit: _Unit, text: str, config: ChunkConfig) -> list[_Range]:
    """Turn one section into chunk offset ranges."""
    pieces = _unit_pieces(unit, text, config)
    if not pieces:
        return []

    heading = None
    if unit.blocks and unit.blocks[0].kind == "heading":
        # Use the heading block itself, not pieces[0]: the heading may have been
        # filtered out by skip_prefixes / skip_kinds, leaving the body first.
        heading = (unit.blocks[0].start, unit.blocks[0].end)

    ranges: list[_Range] = []
    for piece in pieces:
        fits = ranges and not piece.hard_break and piece.end - ranges[-1].start <= config.max_chars
        # A section heading always travels with the first piece of its body,
        # even when that body is a single oversized block.
        heading_only = (
            not piece.hard_break
            and bool(ranges)
            and heading is not None
            and ranges[-1].start == heading[0]
            and ranges[-1].end <= heading[1]
        )
        if fits or heading_only:
            ranges[-1].end = piece.end
            ranges[-1].pieces.append(piece)
        else:
            ranges.append(_Range(piece.start, piece.end, [piece]))

    if ranges and heading is not None and [ranges[0].start, ranges[0].end] == list(heading):
        # A heading with no body (or followed by a skipped block) is not a chunk.
        ranges.pop(0)

    return ranges


def _describe(rng: _Range) -> tuple[str, str]:
    """Dominant block kind and language for a chunk range."""
    kinds = {piece.kind for piece in rng.pieces if piece.kind != "heading"}
    if not kinds:  # pragma: no cover - heading-only ranges are dropped
        return "text", ""
    if len(kinds) > 1:
        return "mixed", ""

    kind = next(iter(kinds))
    if kind != "code":
        return kind, ""
    langs = {piece.lang for piece in rng.pieces if piece.kind == "code" and piece.lang}
    return kind, (langs.pop() if len(langs) == 1 else "")


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
    for unit in _build_units(parse_blocks(text)):
        context = " > ".join(title for _, title in unit.headings)
        first_block = unit.blocks[0] if unit.blocks else None
        for rng in _emit_unit(unit, text, settings):
            if not text[rng.start : rng.end].strip():  # pragma: no cover
                continue
            kind, lang = _describe(rng)
            chunks.append(
                RawChunk(
                    start=rng.start,
                    end=rng.end,
                    start_line=_line_number(line_starts, rng.start),
                    end_line=_line_number(line_starts, max(rng.start, rng.end - 1)),
                    context=context,
                    headings_with_levels=unit.headings,
                    starts_with_heading=first_block is not None
                    and first_block.kind == "heading"
                    and first_block.start == rng.start,
                    kind=kind,
                    lang=lang,
                )
            )
    return chunks


__all__ = ["RawChunk", "split_text"]
