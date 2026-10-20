"""langchain-md-chunker: MDX-aware markdown chunking with source offsets.

Public API::

    from langchain_md_chunker import Chunker, ChunkConfig

    chunker = Chunker(ChunkConfig(max_chars=1200))
    chunks = chunker.split_file("docs/page.md")
    chunks[0].text == Path("docs/page.md").read_text()[chunks[0].start:chunks[0].end]

Only the names in ``__all__`` are public. The parsing/splitting internals
(``blocks`` / ``splitter``) are implementation details and may change without
notice. Corpus-specific rules live in :mod:`langchain_md_chunker.presets`.
"""

from __future__ import annotations

from .chunker import DEFAULT_PATTERNS, Chunker
from .config import ChunkConfig
from .integrations import to_langchain_documents
from .models import Chunk
from .presets import langchain_docs
from .storage import (
    CHUNKS_FILE,
    MANIFEST_FILE,
    build_manifest,
    read_chunks,
    read_manifest,
    write_chunks,
)
from .verify import verify_chunks

__version__ = "0.1.0"

__all__ = [
    "CHUNKS_FILE",
    "DEFAULT_PATTERNS",
    "MANIFEST_FILE",
    "Chunk",
    "ChunkConfig",
    "Chunker",
    "__version__",
    "build_manifest",
    "langchain_docs",
    "read_chunks",
    "read_manifest",
    "to_langchain_documents",
    "verify_chunks",
    "write_chunks",
]
