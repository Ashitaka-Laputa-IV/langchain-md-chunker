"""langchain-md-chunker: MDX-aware markdown chunking with source offsets.

Public API::

    from langchain_md_chunker import Chunker, ChunkConfig

    chunker = Chunker(ChunkConfig(max_chars=1200))
    chunks = chunker.split_file("docs/page.md")
    chunks[0].text == Path("docs/page.md").read_text()[chunks[0].start:chunks[0].end]

Corpus-independent core plus opt-in presets (see
:func:`langchain_md_chunker.presets.langchain_docs`). No third-party runtime
dependencies: parsing, chunking and storage use the standard library only.
"""

from __future__ import annotations

from .blocks import Block, Line, parse_blocks
from .chunker import DEFAULT_PATTERNS, Chunker
from .config import ChunkConfig
from .models import Chunk
from .presets import langchain_docs
from .splitter import RawChunk, split_text
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
    "Block",
    "Chunk",
    "ChunkConfig",
    "Chunker",
    "Line",
    "RawChunk",
    "__version__",
    "build_manifest",
    "langchain_docs",
    "parse_blocks",
    "read_chunks",
    "read_manifest",
    "split_text",
    "verify_chunks",
    "write_chunks",
]
