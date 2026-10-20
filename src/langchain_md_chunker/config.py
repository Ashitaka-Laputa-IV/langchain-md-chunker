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

#: Supported chunk id schemes.
ID_STRATEGIES: tuple[str, ...] = ("location", "content")


@dataclass(frozen=True, slots=True)
class ChunkConfig:
    """Parameters controlling how a document is split.

    Args:
        max_chars: Soft upper bound for a chunk, measured in characters of the
            source document. Oversized multi-line blocks are split at line
            boundaries (and semantically re-wrapped in ``Chunk.content``). Only
            a *single line* longer than ``max_chars``, or a delimiter-only tail
            folded into the previous fragment, can exceed the bound; cutting
            inside a line would corrupt the text.
        skip_kinds: Block kinds that are dropped instead of being chunked.
        skip_prefixes: Blocks whose stripped text starts with one of these
            prefixes are dropped as boilerplate. Empty by default; presets such
            as :func:`langchain_md_chunker.presets.langchain_docs` fill it in.
        include_headings: When true, ``Chunk.content`` is prefixed with the
            section heading path (``# A`` / ``## B`` / ``### C``), which is
            usually better input for embeddings. ``Chunk.text`` always stays an
            exact slice of the source document.
        min_chars: When positive, sibling sections smaller than this are merged
            into one chunk (as long as the result still fits in ``max_chars``).
            ``0`` disables section merging.
        merge_small_sections: Set to false to keep every section separate even
            when ``min_chars`` is positive.
        id_strategy: ``"location"`` (default) derives the id from the document
            path and offsets, so the same slice always gets the same id.
            ``"content"`` derives it from ``Chunk.content``, so identical chunks
            share an id even when they live in different files.
    """

    max_chars: int = 1500
    skip_kinds: tuple[str, ...] = DEFAULT_SKIP_KINDS
    skip_prefixes: tuple[str, ...] = ()
    include_headings: bool = False
    min_chars: int = 0
    merge_small_sections: bool = True
    id_strategy: str = "location"

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if not 0 <= self.min_chars <= self.max_chars:
            raise ValueError("min_chars must be between 0 and max_chars")
        if any(not prefix.strip() for prefix in self.skip_prefixes):
            raise ValueError("skip_prefixes must not contain blank prefixes")
        if self.id_strategy not in ID_STRATEGIES:
            raise ValueError(f"id_strategy must be one of {ID_STRATEGIES}")


__all__ = ["DEFAULT_SKIP_KINDS", "ID_STRATEGIES", "ChunkConfig"]
