"""High level API: turn files or directory trees into :class:`Chunk` objects."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from pathlib import Path

from .config import ChunkConfig
from .models import Chunk
from .splitter import RawChunk, split_text

#: Default file patterns understood by :meth:`Chunker.split_directory`.
DEFAULT_PATTERNS: tuple[str, ...] = ("*.md", "*.mdx", "*.MD", "*.MDX")

#: Accepted values for :meth:`Chunker.split_directory`'s ``on_error``.
ON_ERROR_MODES: tuple[str, ...] = ("raise", "skip")

#: Directories never traversed by :meth:`Chunker.split_directory`.
IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)


def _chunk_id(doc: str, start: int, end: int, content: str, strategy: str) -> str:
    """Stable, filesystem-friendly id: ``c`` + 16 hex characters."""
    payload = (
        f"content\0{content}"
        if strategy == "content"
        else f"{doc}\0{start}\0{end}"
    )
    digest = hashlib.sha1(payload.encode()).hexdigest()
    return f"c{digest[:16]}"


def _heading_prefix(raw: RawChunk) -> str:
    """Rebuild the section path as markdown headings (``# A`` / ``## B``)."""
    headings = raw.headings_with_levels
    if raw.starts_with_heading and headings:
        # The slice already opens with its own heading: only add the ancestors.
        headings = headings[:-1]

    lines = [f"{'#' * level} {title.strip()}" for level, title in headings if title.strip()]
    return "\n".join(lines)


def _build_content(raw: RawChunk, body: str, config: ChunkConfig) -> str:
    """Chunk body plus synthesised context (heading path and block wrappers).

    ``Chunk.text`` stays an exact source slice; only ``Chunk.content`` may carry
    the heading prefix, a reopened code fence, a repeated table header or an MDX
    component annotation.
    """
    parts = []
    if config.include_headings:
        heading = _heading_prefix(raw)
        if heading:
            parts.append(heading)
    if raw.prefix:
        parts.append(raw.prefix)
    prefix = "\n\n".join(parts)
    if prefix and not prefix.endswith("\n"):
        prefix += "\n\n"
    return f"{prefix}{body}{raw.suffix}"


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
        chunks: list[Chunk] = []
        for raw in split_text(text, self.config):
            body = text[raw.start : raw.end]
            content = _build_content(raw, body, self.config)
            chunks.append(
                Chunk(
                    id=_chunk_id(doc, raw.start, raw.end, content, self.config.id_strategy),
                    doc=doc,
                    start=raw.start,
                    end=raw.end,
                    start_line=raw.start_line,
                    end_line=raw.end_line,
                    headings=raw.headings,
                    context=raw.context,
                    text=body,
                    content=content,
                    kind=raw.kind,
                    lang=raw.lang,
                )
            )
        return chunks

    def split_file(
        self,
        path: str | Path,
        *,
        root: str | Path | None = None,
        encoding: str = "utf-8",
    ) -> list[Chunk]:
        """Split one file. ``doc`` becomes the path relative to ``root``."""
        file_path = Path(path)
        text = file_path.read_text(encoding=encoding)
        base = Path(root) if root is not None else file_path.parent
        try:
            doc = file_path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            doc = file_path.name
        return self.split_text(text, doc=doc)

    def iter_directory(
        self,
        root: str | Path,
        patterns: Sequence[str] = DEFAULT_PATTERNS,
        *,
        encoding: str = "utf-8",
        on_error: str = "raise",
    ) -> Iterator[Chunk]:
        """Yield chunks file by file, in a stable order.

        Args:
            root: Directory to walk.
            patterns: Glob patterns selecting files.
            encoding: Encoding used to read each file.
            on_error: ``"raise"`` (default) propagates read/decoding errors;
                ``"skip"`` silently ignores unreadable files, which is useful
                for mixed-encoding corpora.
        """
        if on_error not in ON_ERROR_MODES:
            raise ValueError(f"on_error must be one of {ON_ERROR_MODES}")

        base = Path(root)
        if not base.is_dir():
            raise NotADirectoryError(f"not a directory: {base}")

        files: list[Path] = sorted(
            {
                path
                for pattern in patterns
                for path in base.rglob(pattern)
                if not IGNORED_DIRS.intersection(path.relative_to(base).parts)
            },
            key=lambda path: path.as_posix(),
        )
        def generate() -> Iterator[Chunk]:
            for file_path in files:
                try:
                    yield from self.split_file(file_path, root=base, encoding=encoding)
                except (OSError, UnicodeDecodeError):
                    if on_error == "raise":
                        raise

        # Validate eagerly: the caller gets the error here, not on first next().
        return generate()

    def split_directory(
        self,
        root: str | Path,
        patterns: Sequence[str] = DEFAULT_PATTERNS,
        *,
        encoding: str = "utf-8",
        on_error: str = "raise",
    ) -> list[Chunk]:
        """Split every matching file under ``root``, in a stable order.

        A thin materialisation of :meth:`iter_directory`; use the iterator for
        very large corpora to keep only one file's chunks in memory.
        """
        return list(self.iter_directory(root, patterns, encoding=encoding, on_error=on_error))


__all__ = ["DEFAULT_PATTERNS", "IGNORED_DIRS", "ON_ERROR_MODES", "Chunker"]
