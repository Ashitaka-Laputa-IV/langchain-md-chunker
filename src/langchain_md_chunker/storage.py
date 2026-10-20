"""Persistence: a JSONL chunk store plus a small JSON manifest.

Layout of the output directory::

    <out>/chunks.jsonl    # one JSON object per chunk, source order
    <out>/manifest.json   # source root, config and aggregate stats

JSONL keeps the store append/stream friendly: a demo or a loader can read it
line by line without materialising the whole corpus.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from .config import ChunkConfig
from .models import Chunk

CHUNKS_FILE = "chunks.jsonl"
MANIFEST_FILE = "manifest.json"
FORMAT_VERSION = 1


def _atomic_write(path: Path, writer: Callable[[TextIO], None]) -> None:
    """Write via a sibling temp file + ``os.replace`` so readers never see half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            writer(handle)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def write_chunks(
    chunks: Iterable[Chunk],
    out_dir: str | Path,
    *,
    manifest: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write chunks (and optionally a manifest) to ``out_dir``.

    Each file is replaced atomically (temp file + :func:`os.replace`), so a
    concurrent reader never sees a truncated file. The two files are replaced
    one after the other, not in a single transaction: a reader that reloads in
    between may briefly see new chunks next to the previous manifest.
    """
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    chunks_path = directory / CHUNKS_FILE

    def write_jsonl(handle: TextIO) -> None:
        for chunk in chunks:
            handle.write(json.dumps(chunk.to_dict(), ensure_ascii=False))
            handle.write("\n")

    _atomic_write(chunks_path, write_jsonl)

    manifest_path = directory / MANIFEST_FILE
    if manifest is not None:
        payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        _atomic_write(manifest_path, lambda handle: handle.write(payload))
    return chunks_path, manifest_path


def read_chunks(path: str | Path) -> list[Chunk]:
    """Read a chunk store, accepting either a directory or a ``.jsonl`` file."""
    target = Path(path)
    if target.is_dir():
        target = target / CHUNKS_FILE

    chunks: list[Chunk] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                chunks.append(Chunk.from_dict(json.loads(line)))
    return chunks


def read_manifest(out_dir: str | Path) -> dict[str, Any]:
    """Read the manifest of a chunk store (empty dict when absent)."""
    path = Path(out_dir) / MANIFEST_FILE
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_manifest(
    chunks: Sequence[Chunk],
    *,
    source_root: str | Path,
    config: ChunkConfig,
) -> dict[str, Any]:
    """Summarise a chunking run for the store's ``manifest.json``."""
    docs = {chunk.doc for chunk in chunks}
    sizes = [chunk.chars for chunk in chunks]
    return {
        "format_version": FORMAT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_root": str(Path(source_root).resolve()),
        "config": {
            "max_chars": config.max_chars,
            "skip_kinds": list(config.skip_kinds),
            "skip_prefixes": list(config.skip_prefixes),
            "include_headings": config.include_headings,
        },
        "doc_count": len(docs),
        "chunk_count": len(chunks),
        "total_chars": sum(sizes),
        "chunk_chars_min": min(sizes, default=0),
        "chunk_chars_avg": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "chunk_chars_max": max(sizes, default=0),
    }


__all__ = [
    "CHUNKS_FILE",
    "FORMAT_VERSION",
    "MANIFEST_FILE",
    "build_manifest",
    "read_chunks",
    "read_manifest",
    "write_chunks",
]
