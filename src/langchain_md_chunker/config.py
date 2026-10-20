"""Chunking configuration.

The defaults are deliberately corpus-agnostic: quirks of a specific
documentation set belong in :mod:`langchain_md_chunker.presets`, not in the
library defaults.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Block kinds that never produce chunk content, regardless of the corpus:
#: YAML frontmatter, inline JS (``export`` / ``import``) and MDX comments.
DEFAULT_SKIP_KINDS: tuple[str, ...] = ("frontmatter", "export", "import", "comment")


@dataclass(frozen=True, slots=True)
class ChunkConfig:
    """Parameters controlling how a document is split.

    Args:
        max_chars: Soft upper bound for a chunk, measured in characters of the
            source document. Only atomic blocks (a single code fence, table or
            paragraph) may exceed it.
        skip_kinds: Block kinds that are dropped instead of being chunked.
        skip_prefixes: Blocks whose stripped text starts with one of these
            prefixes are dropped as boilerplate. Empty by default; presets such
            as :func:`langchain_md_chunker.presets.langchain_docs` fill it in.
        include_headings: When true, ``Chunk.content`` is prefixed with the
            section heading path (``# A`` / ``## B`` / ``### C``), which is
            usually better input for embeddings. ``Chunk.text`` always stays an
            exact slice of the source document.
    """

    max_chars: int = 1500
    skip_kinds: tuple[str, ...] = DEFAULT_SKIP_KINDS
    skip_prefixes: tuple[str, ...] = ()
    include_headings: bool = False

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if any(not prefix.strip() for prefix in self.skip_prefixes):
            raise ValueError("skip_prefixes must not contain blank prefixes")


__all__ = ["DEFAULT_SKIP_KINDS", "ChunkConfig"]
