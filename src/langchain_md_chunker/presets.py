"""Corpus presets.

The chunker itself knows nothing about a particular documentation site. Known
corpora are described here as small factories returning a :class:`ChunkConfig`,
so the generic API stays free of corpus-specific defaults.
"""

from __future__ import annotations

from .config import DEFAULT_SKIP_KINDS, ChunkConfig

#: Boilerplate repeated on every page of the LangChain documentation and worth
#: dropping: the "documentation index" banner and the footer with edit links.
LANGCHAIN_DOCS_SKIP_PREFIXES: tuple[str, ...] = (
    "> ## Documentation Index",
    '<div className="source-links">',
    "<a id=",
)


def langchain_docs(
    *,
    max_chars: int = 1500,
    include_headings: bool = False,
    min_chars: int = 0,
    merge_small_sections: bool = True,
    id_strategy: str = "location",
) -> ChunkConfig:
    """Config for the LangChain docs corpus (used by the demo and the tests)."""
    return ChunkConfig(
        max_chars=max_chars,
        skip_kinds=(*DEFAULT_SKIP_KINDS, "rule"),
        skip_prefixes=LANGCHAIN_DOCS_SKIP_PREFIXES,
        include_headings=include_headings,
        min_chars=min_chars,
        merge_small_sections=merge_small_sections,
        id_strategy=id_strategy,
    )


__all__ = ["LANGCHAIN_DOCS_SKIP_PREFIXES", "langchain_docs"]
