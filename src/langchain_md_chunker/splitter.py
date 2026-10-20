"""Section grouping and chunk assembly.

Consumes the blocks produced by :mod:`langchain_md_chunker.blocks`, groups them by
heading hierarchy, and packs each section into offset ranges <= ``max_chars``.
Chunks are *ranges only*: the source text is never duplicated or rewritten.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from .blocks import MDX_OPEN_RE, Block, parse_blocks, split_lines
from .config import ChunkConfig


@dataclass(frozen=True, slots=True)
class RawChunk:
    """A chunk before it is bound to a document path.

    ``headings_with_levels`` keeps the original heading depth so a caller can
    rebuild the section path verbatim (``# A`` / ``## B`` / ``### C``).
    ``starts_with_heading`` is true when the chunk slice already begins with its
    own section heading, in which case that heading must not be duplicated when
    embedding the path into the chunk content.

    ``prefix`` / ``suffix`` are *synthesised* delimiters for a fragment of an
    oversized code fence, table or MDX component (for example a reopened
    ```` ```python ```` line). They belong to ``Chunk.content`` only: ``text``
    stays an exact source slice.
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
    prefix: str = ""
    suffix: str = ""

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
    prefix: str = ""
    suffix: str = ""
    isolated: bool = False


@dataclass(slots=True)
class _Range:
    start: int
    end: int
    pieces: list[_Piece]
    prefix: str = ""
    suffix: str = ""


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

    # Do not leave a lone closing fence (or ``</Tabs>``) as a chunk of its own:
    # fold a delimiter-only tail into the previous fragment. It may exceed
    # max_chars by a few characters, but the fragment stays well-formed.
    if len(spans) > 1:
        tail = text[spans[-1][0] : spans[-1][1]].strip()
        delimiter = (
            block.kind == "code" and bool(tail) and set(tail) <= {"`", "~"}
        ) or (block.kind == "mdx" and tail.startswith("</"))
        if delimiter:
            spans[-2] = (spans[-2][0], spans[-1][1])
            spans.pop()

    return spans


_FENCE_OPEN_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")


def _code_wrapper(
    block: Block, text: str, partial_start: bool, partial_end: bool
) -> tuple[str, str]:
    """Reopen / close the fence around a fragment of a split code block."""
    first = text[block.start : block.end].split("\n", 1)[0].strip()
    match = _FENCE_OPEN_RE.match(first)
    fence = match.group("fence") if match else "```"
    opening = first if match else "```"
    return (f"{opening}\n" if partial_start else "", f"\n{fence}" if partial_end else "")


def _table_header(block: Block, text: str) -> str:
    """Header row (plus alignment row when present) to repeat in table fragments."""
    lines = text[block.start : block.end].split("\n")
    if not lines:  # pragma: no cover - a parsed block is never empty
        return ""
    header = [lines[0]]
    second = next(iter(lines[1:2]), "")
    rule = second.strip()
    if rule and "-" in rule and all(char in "|:- \t" for char in rule):
        header.append(second)
    return "\n".join(header) + "\n"


def _mdx_wrapper(
    block: Block, text: str, partial_start: bool, partial_end: bool
) -> tuple[str, str]:
    """Annotate a fragment of a split MDX component with the component name."""
    first = text[block.start : block.end].split("\n", 1)[0].strip()
    match = MDX_OPEN_RE.match(first)
    name = match.group("name") if match else "MDX"
    return (
        f"{{/* <{name}> */}}\n" if partial_start else "",
        f"\n{{/* </{name}> */}}" if partial_end else "",
    )


def _unit_pieces(unit: _Unit, text: str, config: ChunkConfig) -> list[_Piece]:
    """Flatten a section into packable pieces.

    Blocks of a skipped kind (frontmatter, ``export`` helpers) become a *hard
    break*: the next piece starts a new chunk, so those blocks never leak into a
    chunk as part of the gap between two kept blocks.

    When an oversized code fence / table / MDX component has to be split, each
    fragment keeps enough context to stand on its own: fences are reopened, the
    table header is repeated, and MDX fragments carry their component name.
    Those pieces are *isolated*: two fragments of one block never share a chunk,
    so the wrapper stays balanced.
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
        fragment = len(spans) > 1
        table_header = _table_header(block, text) if fragment and block.kind == "table" else ""

        for start, end in spans:
            prefix = suffix = ""
            if fragment:
                partial_start = start > block.start
                partial_end = end < block.end
                if block.kind == "code":
                    prefix, suffix = _code_wrapper(block, text, partial_start, partial_end)
                elif block.kind == "table":
                    prefix = table_header if partial_start else ""
                elif block.kind == "mdx":
                    prefix, suffix = _mdx_wrapper(block, text, partial_start, partial_end)
            pieces.append(
                _Piece(
                    start,
                    end,
                    hard_break,
                    block.kind,
                    block.lang,
                    prefix,
                    suffix,
                    fragment,
                )
            )
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
        previous = ranges[-1] if ranges else None
        previous_isolated = bool(previous and previous.pieces[-1].isolated)
        fits = (
            previous is not None
            and not piece.hard_break
            and not piece.isolated
            and not previous_isolated
            and piece.end - previous.start <= config.max_chars
        )
        # A section heading always travels with the first piece of its body,
        # even when that body is a single oversized block.
        heading_only = (
            not piece.hard_break
            and previous is not None
            and heading is not None
            and previous.start == heading[0]
            and previous.end <= heading[1]
        )
        if fits or heading_only:
            if heading_only:
                previous.prefix = piece.prefix
            previous.end = piece.end
            previous.suffix = piece.suffix
            previous.pieces.append(piece)
        else:
            ranges.append(_Range(piece.start, piece.end, [piece], piece.prefix, piece.suffix))

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


def _unit_bounds(unit: _Unit) -> tuple[int, int]:
    """Offsets spanning a section (separators included).

    Only called for sections without skipped blocks, so the bounds are simply
    the first and last block of the unit.
    """
    return unit.blocks[0].start, unit.blocks[-1].end


def _can_merge(previous: _Unit, unit: _Unit, config: ChunkConfig) -> bool:
    """Whether two adjacent sections are mergeable siblings.

    Only same-level sections under the *same parent* merge, so a subsection is
    never folded into its parent's sibling. At least one side must be smaller
    than ``min_chars``, and the resulting range (including the separators
    between the two sections) must still fit in ``max_chars``.
    """
    previous_bounds = _unit_bounds(previous)
    bounds = _unit_bounds(unit)
    previous_size = previous_bounds[1] - previous_bounds[0]
    size = bounds[1] - bounds[0]
    if bounds[1] - previous_bounds[0] > config.max_chars:
        return False
    if previous_size >= config.min_chars and size >= config.min_chars:
        return False
    if not unit.headings or len(previous.headings) != len(unit.headings):
        return False
    if previous.headings[-1][0] != unit.headings[-1][0]:
        return False
    return previous.headings[:-1] == unit.headings[:-1]


def _has_skipped(unit: _Unit, text: str, config: ChunkConfig) -> bool:
    """Whether a section contains a dropped block (which forces a hard break)."""
    for block in unit.blocks:
        snippet = text[block.start : block.end].lstrip()
        if block.kind in config.skip_kinds or snippet.startswith(config.skip_prefixes):
            return True
    return False


def _merge_small_sections(units: list[_Unit], text: str, config: ChunkConfig) -> list[_Unit]:
    """Merge small sibling sections into one unit (``min_chars``)."""
    if not config.merge_small_sections or config.min_chars <= 0:
        return units

    merged: list[_Unit] = []
    blocked: list[bool] = []
    for unit in units:
        skipped = _has_skipped(unit, text, config)
        # A skipped block forces a hard break; merging across it would attach the
        # second section's chunks to the first section's heading path.
        if (
            merged
            and not blocked[-1]
            and not skipped
            and _can_merge(merged[-1], unit, config)
        ):
            merged[-1].blocks.extend(unit.blocks)
        else:
            merged.append(_Unit(unit.headings, list(unit.blocks)))
            blocked.append(skipped)
    return merged


def split_text(text: str, config: ChunkConfig | None = None) -> list[RawChunk]:
    """Split ``text`` into chunks addressed by character offsets."""
    settings = config or ChunkConfig()
    if not text.strip():
        return []

    line_starts = [0]
    for position, char in enumerate(text):
        if char == "\n":
            line_starts.append(position + 1)

    units = _merge_small_sections(_build_units(parse_blocks(text)), text, settings)
    chunks: list[RawChunk] = []
    for unit in units:
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
                    prefix=rng.prefix,
                    suffix=rng.suffix,
                )
            )
    return chunks


__all__ = ["RawChunk", "split_text"]
