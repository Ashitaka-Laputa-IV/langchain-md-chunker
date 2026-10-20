"""Command line interface: ``uv run chunk``."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .chunker import DEFAULT_PATTERNS, Chunker
from .config import ChunkConfig
from .presets import langchain_docs
from .storage import build_manifest, write_chunks
from .verify import verify_chunks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chunk",
        description="Split markdown/MDX documents into chunks with source offsets.",
    )
    parser.add_argument("input", help="source directory to split")
    parser.add_argument(
        "-o",
        "--output",
        default="data/chunks",
        help="output directory for the chunk store (default: data/chunks)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=1500,
        help="soft upper bound of one chunk in characters (default: 1500)",
    )
    parser.add_argument(
        "--preset",
        choices=("langchain-docs", "generic"),
        default="langchain-docs",
        help="corpus preset controlling boilerplate dropping (default: langchain-docs)",
    )
    parser.add_argument(
        "--include-headings",
        action="store_true",
        help="prepend the section heading path (# A / ## B) to chunk content",
    )
    parser.add_argument(
        "-p",
        "--pattern",
        dest="patterns",
        action="append",
        help="file pattern, repeatable (default: *.md and *.mdx)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="re-read the sources and verify every chunk offset before writing",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print errors and warnings",
    )
    return parser


def _build_config(args: argparse.Namespace) -> ChunkConfig:
    """Resolve the corpus preset into a concrete config."""
    if args.preset == "langchain-docs":
        return langchain_docs(max_chars=args.max_chars, include_headings=args.include_headings)
    return ChunkConfig(max_chars=args.max_chars, include_headings=args.include_headings)


def _count(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source = Path(args.input)
    if not source.is_dir():
        print(f"error: source directory not found: {source}", file=sys.stderr)
        return 2

    try:
        config = _build_config(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    chunker = Chunker(config)
    patterns = args.patterns or DEFAULT_PATTERNS
    try:
        chunks = chunker.split_directory(source, patterns=patterns)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: failed to read source files: {exc}", file=sys.stderr)
        return 1

    if not chunks:
        print(
            f"warning: no files matched {', '.join(patterns)} under {source}; "
            "writing an empty index",
            file=sys.stderr,
        )

    if args.verify:
        problems = verify_chunks(chunks, source)
        if problems:
            for problem in problems:
                print(f"error: {problem}", file=sys.stderr)
            return 1

    manifest = build_manifest(chunks, source_root=source, config=config)
    try:
        chunks_path, manifest_path = write_chunks(chunks, args.output, manifest=manifest)
    except OSError as exc:
        print(f"error: failed to write {args.output}: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    if not args.quiet:
        print(
            f"{_count(manifest['doc_count'], 'document')} -> "
            f"{_count(manifest['chunk_count'], 'chunk')} "
            f"(avg {manifest['chunk_chars_avg']} chars, "
            f"max {manifest['chunk_chars_max']}), {elapsed:.2f}s"
        )
        print(f"chunks  : {chunks_path}")
        print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
