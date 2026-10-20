"""Output model produced by the chunker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Chunk:
    """A contiguous slice of a source document plus its retrieval metadata.

    Offsets are half-open Unicode code point offsets into the decoded source
    text, i.e. ``source[start:end] == chunk.text`` always holds. Line numbers are
    1-based and inclusive.

    ``content`` is what a consumer should embed or display: it equals ``text``
    unless :attr:`langchain_md_chunker.config.ChunkConfig.include_headings` is
    enabled, in which case the section heading path is prepended.

    ``kind`` is the dominant block kind (``para`` / ``code`` / ``table`` /
    ``list`` / ``quote`` / ``mdx`` / ``mixed``), and ``lang`` is the fence
    language when the chunk consists of a single code block.
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
    kind: str = "text"
    lang: str = ""

    def __post_init__(self) -> None:
        # ``content`` defaults to the source slice, so callers that never ask for
        # heading prefixes cannot accidentally embed an empty string.
        if not self.content:
            object.__setattr__(self, "content", self.text)

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
            "content": self.content,
            "kind": self.kind,
            "lang": self.lang,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chunk:
        """Inverse of :meth:`to_dict`."""
        start = int(data["start"])
        end = int(data["end"])
        if start < 0 or end < start:
            raise ValueError(f"invalid chunk offsets: start={start}, end={end}")
        return cls(
            id=str(data["id"]),
            doc=str(data["doc"]),
            start=start,
            end=end,
            start_line=int(data.get("start_line", 0)),
            end_line=int(data.get("end_line", 0)),
            headings=tuple(str(item) for item in data.get("headings") or ()),
            context=str(data.get("context", "")),
            text=str(data.get("text", "")),
            content=str(data.get("content") or ""),
            kind=str(data.get("kind") or "text"),
            lang=str(data.get("lang") or ""),
        )


__all__ = ["Chunk"]
