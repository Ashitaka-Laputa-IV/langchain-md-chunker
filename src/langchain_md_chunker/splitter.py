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
    lines = split_lines(text[block.start : block.end])
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
                    context=context,
                    headings_with_levels=unit.headings,
                    starts_with_heading=first_block is not None
                    and first_block.kind == "heading"
                    and first_block.start == start,
                )
            )
    return chunks


__all__ = [
    "Block",
    "RawChunk",
    "build_units",
    "parse_blocks",
    "split_text",
]

__all__ = ["RawChunk", "build_units", "split_text"]
