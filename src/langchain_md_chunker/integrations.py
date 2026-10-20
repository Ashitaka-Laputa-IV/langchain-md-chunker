"""Optional adapters for downstream frameworks.

These functions never add a runtime dependency: the third-party package is
imported lazily, so the core stays usable without it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from .models import Chunk


def to_langchain_documents(
    chunks: Iterable[Chunk],
    *,
    page_content: Literal["content", "text"] = "content",
) -> list[Any]:
    """Convert chunks into ``langchain_core.documents.Document`` objects.

    Args:
        chunks: chunks produced by :class:`langchain_md_chunker.Chunker`.
        page_content: which field becomes the document text. ``"content"``
            (default) keeps the optional heading prefix; ``"text"`` uses the
            exact source slice.

    Returns:
        A list of ``Document`` instances. Metadata keys: ``id``, ``source``
        (alias of ``doc``), ``doc``, ``start``, ``end``, ``start_line``,
        ``end_line``, ``chars``, ``headings``, ``context``.

    Raises:
        ImportError: ``langchain-core`` is not installed.
        ValueError: ``page_content`` is neither ``"content"`` nor ``"text"``.
    """
    if page_content not in {"content", "text"}:
        raise ValueError("page_content must be 'content' or 'text'")

    try:
        from langchain_core.documents import Document
    except ImportError as exc:
        raise ImportError(
            "to_langchain_documents() requires langchain-core; "
            "install it with `pip install langchain-core`"
        ) from exc

    documents: list[Any] = []
    for chunk in chunks:
        documents.append(
            Document(
                page_content=getattr(chunk, page_content),
                metadata={
                    "id": chunk.id,
                    "source": chunk.doc,
                    "doc": chunk.doc,
                    "start": chunk.start,
                    "end": chunk.end,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chars": chunk.chars,
                    "headings": list(chunk.headings),
                    "context": chunk.context,
                },
            )
        )
    return documents


__all__ = ["to_langchain_documents"]
