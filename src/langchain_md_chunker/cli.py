"""Command line interface: ``uv run chunk``."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .chunker import DEFAULT_PATTERNS, Chunker, verify_chunks
from .models import ChunkConfig
from .storage import build_manifest, write_chunks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chunk",
        description="将 markdown/MDX 文档切分为带字符偏移元数据的 chunk，并写入本地 JSONL。",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="data/langchain-docs",
        help="源文档目录（默认 data/langchain-docs）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="data/chunks",
        help="chunk 输出目录（默认 data/chunks）",
    )
    parser.add_argument("--max-chars", type=int, default=1500, help="单个 chunk 的目标上限字符数")
    parser.add_argument(
        "-p",
        "--pattern",
        dest="patterns",
        action="append",
        help="文件匹配模式，可重复（默认 *.md 与 *.mdx）",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="写盘前重新读取源文件，校验每个 chunk 的偏移切片",
    )
    parser.add_argument("--quiet", action="store_true", help="只输出错误信息")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source = Path(args.input)
    if not source.is_dir():
        print(f"错误：源目录不存在 {source}", file=sys.stderr)
        return 2

    try:
        config = ChunkConfig(max_chars=args.max_chars)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    chunker = Chunker(config)
    patterns = args.patterns or DEFAULT_PATTERNS
    chunks = chunker.split_directory(source, patterns=patterns)

    if not chunks:
        print(
            f"警告：{source} 下没有匹配 {', '.join(patterns)} 的文件，输出为空索引",
            file=sys.stderr,
        )

    if args.verify:
        problems = verify_chunks(chunks, source)
        if problems:
            for problem in problems:
                print(f"错误：{problem}", file=sys.stderr)
            return 1

    manifest = build_manifest(chunks, source_root=source, config=config)
    chunks_path, manifest_path = write_chunks(chunks, args.output, manifest=manifest)
    elapsed = time.perf_counter() - started

    if not args.quiet:
        print(
            f"{manifest['doc_count']} 篇文档 -> {manifest['chunk_count']} 个 chunk "
            f"（平均 {manifest['chunk_chars_avg']} 字符，"
            f"最大 {manifest['chunk_chars_max']}），耗时 {elapsed:.2f}s"
        )
        print(f"chunk: {chunks_path}")
        print(f"清单: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
