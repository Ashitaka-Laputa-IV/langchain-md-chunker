"""Data models shared by the chunker, the CLI and the storage layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Block kinds that never produce chunk content (frontmatter and inline JS
#: helpers such as ``export const Foo = ...`` found in the LangChain docs).
DEFAULT_SKIP_KINDS: tuple[str, ...] = ("frontmatter", "export")

#: Boilerplate that is repeated in every page of the LangChain docs and carries
#: no retrieval value: the "documentation index" banner and the footer with
#: "edit this page" links.
DEFAULT_SKIP_PREFIXES: tuple[str, ...] = (
    "> ## Documentation Index",
    '<div className="source-links">',
)


@dataclass(frozen=True, slots=True)
class ChunkConfig:
    """Parameters controlling how a document is split.

    Args:
        max_chars: Soft upper bound for a chunk, measured in characters of the
            source document. Only atomic blocks (a single code fence, table or
            paragraph) may exceed it.
        skip_kinds: Block kinds that are dropped instead of being chunked.
        skip_prefixes: Blocks whose stripped text starts with one of these
            prefixes are dropped as boilerplate.
        include_headings: When true, ``Chunk.content`` is prefixed with the
            section heading path (``# A`` / ``## B`` / ``### C``), which is
            usually better input for embeddings. ``Chunk.text`` always stays an
            exact slice of the source document.
    """

    max_chars: int = 1500
    skip_kinds: tuple[str, ...] = DEFAULT_SKIP_KINDS
    skip_prefixes: tuple[str, ...] = DEFAULT_SKIP_PREFIXES
    include_headings: bool = False

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if any(not prefix.strip() for prefix in self.skip_prefixes):
            raise ValueError("skip_prefixes must not contain blank prefixes")


@dataclass(frozen=True, slots=True)
class Chunk:
    """A contiguous slice of a source document plus its retrieval metadata.

    Offsets are half-open Unicode code point offsets into the decoded source
    text, i.e. ``source[start:end] == chunk.text`` always holds. Line numbers are
    1-based and inclusive.

    ``content`` is what a consumer should embed or display: it equals ``text``
    unless :attr:`ChunkConfig.include_headings` is enabled, in which case the
    section heading path is prepended.
    """

    id: str
    doc: str
    start: int
    end: int
    start_line: int
    end_line: int
    headings: tuple[str, ...]
    context: str
    text: str
    content: str = ""

    @property
    def chars(self) -> int:
        """Length of the chunk in characters."""
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        """Serialisable representation (JSON friendly)."""
        return {
            "id": self.id,
            "doc": self.doc,
            "start": self.start,
            "end": self.end,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chars": self.chars,
            "headings": list(self.headings),
            "context": self.context,
            "text": self.text,
            "content": self.content or self.text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chunk:
        """Inverse of :meth:`to_dict`."""
        return cls(
            id=str(data["id"]),
            doc=str(data["doc"]),
            start=int(data["start"]),
            end=int(data["end"]),
            start_line=int(data.get("start_line", 0)),
            end_line=int(data.get("end_line", 0)),
            headings=tuple(str(item) for item in data.get("headings") or ()),
            context=str(data.get("context", "")),
            text=str(data.get("text", "")),
            content=str(data.get("content") or data.get("text", "")),
        )
