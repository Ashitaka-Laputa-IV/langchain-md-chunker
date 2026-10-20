"""Cross-check chunks against the files they came from."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .models import Chunk


def verify_chunks(chunks: Iterable[Chunk], root: str | Path) -> list[str]:
    """Re-read sources from disk and check that every chunk matches its offsets.

    Unreadable sources are reported as problems instead of raising, so one broken
    file does not hide every other mismatch. Returns a list of human-readable
    problems; an empty list means everything is consistent.
    """
    base = Path(root)
    texts: dict[str, str] = {}
    unreadable: set[str] = set()
    problems: list[str] = []

    for chunk in chunks:
        if chunk.doc in unreadable:
            continue
        if chunk.doc not in texts:
            try:
                texts[chunk.doc] = (base / chunk.doc).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                unreadable.add(chunk.doc)
                problems.append(f"{chunk.doc}: cannot read source file ({type(exc).__name__})")
                continue

        text = texts[chunk.doc]
        if not 0 <= chunk.start < chunk.end <= len(text):
            problems.append(f"{chunk.id} {chunk.doc}: offsets out of range")
        elif text[chunk.start : chunk.end] != chunk.text:
            problems.append(f"{chunk.id} {chunk.doc}@{chunk.start}:{chunk.end}: slice mismatch")
    return problems


__all__ = ["verify_chunks"]
