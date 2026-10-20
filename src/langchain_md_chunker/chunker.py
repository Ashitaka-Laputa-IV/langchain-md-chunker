"""High level API: turn files or directory trees into :class:`Chunk` objects."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from pathlib import Path

from .models import Chunk, ChunkConfig
from .splitter import RawChunk, split_text

#: Default file patterns understood by :meth:`Chunker.split_directory`.
DEFAULT_PATTERNS: tuple[str, ...] = ("*.md", "*.mdx")


def _chunk_id(doc: str, start: int, end: int) -> str:
    digest = hashlib.sha1(f"{doc}\0{start}\0{end}".encode()).hexdigest()
    return f"c{digest[:11]}"


def _heading_prefix(raw: RawChunk) -> str:
    """Rebuild the section path as markdown headings (``# A`` / ``## B``)."""
    headings = raw.headings_with_levels
    if raw.starts_with_heading and headings:
        # The slice already opens with its own heading: only add the ancestors.
        headings = headings[:-1]

    lines: list[str] = []
    for level, title in headings:
        title = title.strip()
        if title:
            lines.append(f"{'#' * max(1, min(level, 6))} {title}")
    return "\n".join(lines)


def _build_content(raw: RawChunk, text: str, config: ChunkConfig) -> str:
    """Chunk body, optionally prefixed with the heading path.

    ``Chunk.text`` stays an exact source slice; only ``Chunk.content`` may carry
    the synthesised heading prefix.
    """
    body = text[raw.start : raw.end]
    if not config.include_headings:
        return body
    prefix = _heading_prefix(raw)
    return f"{prefix}\n\n{body}" if prefix else body


class Chunker:
    """Split markdown/MDX documents into offset-addressable chunks.

    Example:
        >>> chunker = Chunker(ChunkConfig(max_chars=1200))
        >>> chunks = chunker.split_file("data/langchain-docs/oss/python/learn.md")
        >>> source = Path("data/langchain-docs/oss/python/learn.md").read_text()
        >>> all(source[c.start:c.end] == c.text for c in chunks)
        True
    """

    def __init__(self, config: ChunkConfig | None = None) -> None:
        self.config = config or ChunkConfig()

    def split_text(self, text: str, *, doc: str = "<memory>") -> list[Chunk]:
        """Split in-memory text; ``doc`` is stored as the source identifier."""
        return [
            Chunk(
                id=_chunk_id(doc, raw.start, raw.end),
                doc=doc,
                start=raw.start,
                end=raw.end,
                start_line=raw.start_line,
                end_line=raw.end_line,
                headings=raw.headings,
                context=raw.context,
                text=text[raw.start : raw.end],
                content=_build_content(raw, text, self.config),
            )
            for raw in split_text(text, self.config)
        ]

    def split_file(self, path: str | Path, *, root: str | Path | None = None) -> list[Chunk]:
        """Split one file. ``doc`` becomes the path relative to ``root``."""
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8")
        base = Path(root) if root is not None else file_path.parent
        try:
            doc = file_path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            doc = file_path.name
        return self.split_text(text, doc=doc)

    def split_directory(
        self,
        root: str | Path,
        patterns: Sequence[str] = DEFAULT_PATTERNS,
    ) -> list[Chunk]:
        """Split every matching file under ``root``, in a stable order."""
        base = Path(root)
        if not base.is_dir():
            raise NotADirectoryError(f"not a directory: {base}")

        files: list[Path] = sorted({path for pattern in patterns for path in base.rglob(pattern)})
        chunks: list[Chunk] = []
        for file_path in files:
            chunks.extend(self.split_file(file_path, root=base))
        return chunks


def verify_chunks(chunks: Iterable[Chunk], root: str | Path) -> list[str]:
    """Re-read sources from disk and check that every chunk matches its offsets."""
    base = Path(root)
    cache: dict[str, str] = {}
    problems: list[str] = []

    for chunk in chunks:
        if chunk.doc not in cache:
            cache[chunk.doc] = (base / chunk.doc).read_text(encoding="utf-8")
        text = cache[chunk.doc]
        if not 0 <= chunk.start < chunk.end <= len(text):
            problems.append(f"{chunk.id} {chunk.doc}: 偏移超出文件长度")
        elif text[chunk.start : chunk.end] != chunk.text:
            problems.append(f"{chunk.id} {chunk.doc}@{chunk.start}:{chunk.end} 偏移不匹配")
    return problems


__all__ = ["DEFAULT_PATTERNS", "Chunker", "verify_chunks"]
