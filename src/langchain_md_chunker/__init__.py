"""langchain-md-chunker: MDX-aware markdown chunking with source offsets.

Public API::

    from langchain_md_chunker import Chunker, ChunkConfig

    chunker = Chunker(ChunkConfig(max_chars=1200))
    chunks = chunker.split_file("docs/page.md")
    chunks[0].text == Path("docs/page.md").read_text()[chunks[0].start:chunks[0].end]

The package intentionally has no third-party dependencies: parsing, chunking
and storage are implemented on the standard library only.
"""

from __future__ import annotations

from .chunker import DEFAULT_PATTERNS, Chunker, verify_chunks
from .models import Chunk, ChunkConfig
from .splitter import Block, RawChunk, parse_blocks, split_text
from .storage import (
    CHUNKS_FILE,
    MANIFEST_FILE,
    build_manifest,
    read_chunks,
    read_manifest,
    write_chunks,
)

__version__ = "0.1.0"

__all__ = [
    "CHUNKS_FILE",
    "DEFAULT_PATTERNS",
    "MANIFEST_FILE",
    "Block",
    "Chunk",
    "ChunkConfig",
    "Chunker",
    "RawChunk",
    "__version__",
    "build_manifest",
    "parse_blocks",
    "read_chunks",
    "read_manifest",
    "split_text",
    "verify_chunks",
    "write_chunks",
]


def main() -> None:
    """Console entry point (``langchain-md-chunker``)."""
    from .cli import main as cli_main

    raise SystemExit(cli_main())
