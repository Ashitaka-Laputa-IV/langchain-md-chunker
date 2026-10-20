"""Command line interface: ``uv run chunk``."""

from __future__ import annotations

import argparse
import codecs
import sys
import time
from pathlib import Path

from . import __version__
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
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("input", help="source directory or file to split")
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
        default="generic",
        help="corpus preset controlling boilerplate dropping (default: generic)",
    )
    parser.add_argument(
        "--include-headings",
        action="store_true",
        help="prepend the section heading path (# A / ## B) to chunk content",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=0,
        help="merge sibling sections smaller than this (0 disables merging)",
    )
    parser.add_argument(
        "--no-merge-small-sections",
        action="store_true",
        help="keep every section separate even when --min-chars is set",
    )
    parser.add_argument(
        "--id-strategy",
        choices=("location", "content"),
        default="location",
        help="derive chunk ids from offsets (default) or from content",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="encoding used to read source files (default: utf-8)",
    )
    parser.add_argument(
        "--on-error",
        choices=("raise", "skip"),
        default="raise",
        help="skip unreadable files instead of aborting (default: raise)",
    )
    parser.add_argument(
        "-p",
        "--pattern",
        dest="patterns",
        action="append",
        help="file pattern, repeatable (default: *.md, *.mdx, *.MD, *.MDX)",
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
    options = {
        "max_chars": args.max_chars,
        "include_headings": args.include_headings,
        "min_chars": args.min_chars,
        "merge_small_sections": not args.no_merge_small_sections,
        "id_strategy": args.id_strategy,
    }
    if args.preset == "langchain-docs":
        return langchain_docs(**options)
    return ChunkConfig(**options)


def _count(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source = Path(args.input)
    if not source.exists():
        print(f"error: source path not found: {source}", file=sys.stderr)
        return 2

    try:
        config = _build_config(args)
        codecs.lookup(args.encoding)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except LookupError:
        print(f"error: unknown encoding: {args.encoding}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    chunker = Chunker(config)
    patterns = args.patterns or DEFAULT_PATTERNS
    root = source.parent if source.is_file() else source
    skipped: list[str] = []

    def record_skip(path: Path, exc: Exception) -> None:
        skipped.append(f"{path}: {type(exc).__name__}")

    try:
        if source.is_file():
            chunks = chunker.split_file(source, root=root, encoding=args.encoding)
        else:
            chunks = chunker.split_directory(
                source,
                patterns=patterns,
                encoding=args.encoding,
                on_error=args.on_error,
                on_skip=record_skip if args.on_error == "skip" else None,
            )
    except (OSError, UnicodeDecodeError) as exc:
        if args.on_error != "skip":
            print(f"error: failed to read source files: {exc}", file=sys.stderr)
            return 1
        chunks = []
        record_skip(source, exc)

    if skipped:
        print(
            f"warning: skipped {len(skipped)} unreadable file(s):",
            file=sys.stderr,
        )
        for item in skipped:
            print(f"  {item}", file=sys.stderr)

    if not chunks:
        print(
            f"warning: no files matched {', '.join(patterns)} under {source}; "
            "writing an empty index",
            file=sys.stderr,
        )

    if args.verify:
        problems = verify_chunks(chunks, root, encoding=args.encoding)
        if problems:
            for problem in problems:
                print(f"error: {problem}", file=sys.stderr)
            return 1

    manifest = build_manifest(chunks, source_root=root, config=config)
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
