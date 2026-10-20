"""Minimal demo server for browsing chunks and jumping to source offsets.

This is demo scaffolding only: it uses the standard library, does not import the
chunker package, and only reads the on-disk chunk store.

Usage::

    uv run python demo/server.py                       # http://127.0.0.1:8000
    uv run python demo/server.py --port 9000
    uv run python demo/server.py --chunks data/chunks --source-dir data/langchain-docs
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
PREVIEW_CHARS = 180
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


class ChunkStore:
    """Lazily (re)loads ``chunks.jsonl`` + ``manifest.json`` from disk."""

    def __init__(
        self,
        chunks_dir: str | pathlib.Path,
        source_dir: str | pathlib.Path | None = None,
    ):
        self.dir = pathlib.Path(chunks_dir).expanduser().resolve()
        self.source_override = (
            pathlib.Path(source_dir).expanduser().resolve() if source_dir is not None else None
        )
        self.manifest: dict[str, Any] = {}
        self.chunks: list[dict[str, Any]] = []
        self.docs: dict[str, dict[str, int]] = {}
        self.chunks_payload = b""
        self.manifest_payload = b""
        self.source_root = self.dir
        self._signature: tuple[int, ...] | None = None
        self.reload(force=True)

    # -- loading ---------------------------------------------------------
    def _signature_now(self) -> tuple[int, ...] | None:
        chunks_path = self.dir / "chunks.jsonl"
        if not chunks_path.is_file():
            return None
        stat = chunks_path.stat()
        manifest_path = self.dir / "manifest.json"
        manifest_mtime = manifest_path.stat().st_mtime_ns if manifest_path.is_file() else 0
        return (stat.st_mtime_ns, stat.st_size, manifest_mtime)

    def reload(self, force: bool = False) -> None:
        signature = self._signature_now()
        if signature is None:
            raise FileNotFoundError(f"未找到 {self.dir / 'chunks.jsonl'}")
        if not force and signature == self._signature:
            return

        manifest_path = self.dir / "manifest.json"
        chunks: list[dict[str, Any]] = []
        docs: dict[str, dict[str, int]] = {}
        try:
            manifest = (
                json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file()
                else {}
            )
            with (self.dir / "chunks.jsonl").open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    raw = json.loads(line)
                    text = raw.pop("text", "")
                    content = raw.pop("content", "") or text
                    raw["preview"] = re.sub(r"\s+", " ", content).strip()[:PREVIEW_CHARS]
                    chunks.append(raw)
                    doc = docs.setdefault(raw["doc"], {"chunks": 0, "chars": 0})
                    doc["chunks"] += 1
                    doc["chars"] += int(raw.get("chars", 0))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            # A half-written store (or a file replaced mid-read): keep serving the
            # previous snapshot and retry on the next request.
            self._signature = None
            return

        self._signature = signature
        self.manifest = manifest
        self.chunks = chunks
        self.docs = docs
        self.source_root = self._resolve_source_root()
        # Serialise once per reload: /api/chunks is ~2 MB and is requested on
        # every page load, so re-encoding per request would be wasteful.
        self.chunks_payload = json.dumps(
            {"count": len(chunks), "chunks": chunks}, ensure_ascii=False
        ).encode("utf-8")
        self.manifest_payload = json.dumps(
            {**manifest, **self.stats(), "docs": docs}, ensure_ascii=False
        ).encode("utf-8")

    def _resolve_source_root(self) -> pathlib.Path:
        candidates = [
            self.source_override,
            pathlib.Path(self.manifest["source_root"])
            if self.manifest.get("source_root")
            else None,
            self.dir.parent / "langchain-docs",
        ]
        for candidate in candidates:
            if candidate is not None and candidate.is_dir():
                return candidate.resolve()
        return (self.source_override or self.dir).resolve()

    # -- access ----------------------------------------------------------
    def has_doc(self, doc: str) -> bool:
        return doc in self.docs

    def read_doc(self, doc: str) -> str:
        target = (self.source_root / doc).resolve()
        root = self.source_root.resolve()
        if not target.is_relative_to(root):
            raise PermissionError(f"路径越界: {doc}")
        return target.read_text(encoding="utf-8")

    def stats(self) -> dict[str, Any]:
        return {
            "chunk_count": len(self.chunks),
            "doc_count": len(self.docs),
            "source_root": str(self.source_root),
        }


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "chunk-demo/1.0"
    store: ChunkStore

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path

        if route in ("/", "/index.html"):
            self._send_static("index.html")
        elif route.startswith("/static/"):
            self._send_static(route.removeprefix("/static/"))
        elif route == "/api/manifest":
            self.store.reload()
            self._send_bytes(self.store.manifest_payload, "application/json; charset=utf-8")
        elif route == "/api/chunks":
            self.store.reload()
            self._send_bytes(self.store.chunks_payload, "application/json; charset=utf-8")
        elif route == "/api/doc":
            self._send_doc(urllib.parse.parse_qs(parsed.query))
        elif route == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    # -- helpers ---------------------------------------------------------
    def _send_static(self, name: str) -> None:
        target = (STATIC_DIR / name).resolve()
        if not target.is_relative_to(STATIC_DIR) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        content_type = STATIC_TYPES.get(target.suffix, "application/octet-stream")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_doc(self, query: dict[str, list[str]]) -> None:
        doc = (query.get("path") or [""])[0]
        if not doc or not self.store.has_doc(doc):
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown document")
            return
        try:
            text = self.store.read_doc(doc)
        except (OSError, PermissionError) as exc:
            self.send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        body = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} {format % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demo", description="chunk 浏览演示服务")
    parser.add_argument("--chunks", default="data/chunks", help="chunk 目录（默认 data/chunks）")
    parser.add_argument("--source-dir", default=None, help="源文档目录（默认取 manifest 记录）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    try:
        store = ChunkStore(args.chunks, args.source_dir)
    except FileNotFoundError as exc:
        print(f"错误：{exc}")
        print("请先运行：uv run chunk")
        return 2

    DemoHandler.store = store
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"chunks : {store.dir} ({len(store.chunks)} 个)")
    print(f"source : {store.source_root}")
    print(f"serving: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
