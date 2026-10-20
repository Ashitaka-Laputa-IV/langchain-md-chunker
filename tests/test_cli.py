"""命令行端到端：输出文件、退出码、参数传递。"""

from __future__ import annotations

from pathlib import Path

import pytest

from langchain_md_chunker import CHUNKS_FILE, MANIFEST_FILE
from langchain_md_chunker import cli

DOC = "# Title\n\n" + "\n\n".join(f"paragraph {index} " + "x" * 80 for index in range(4)) + "\n"


def make_tree(root: Path) -> Path:
    source = root / "docs"
    source.mkdir()
    (source / "page.md").write_text(DOC, encoding="utf-8")
    return source


def chunk_count(out: Path) -> int:
    return len((out / CHUNKS_FILE).read_text(encoding="utf-8").splitlines())


def test_cli_writes_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = make_tree(tmp_path)
    out = tmp_path / "chunks"

    assert cli.main([str(source), "-o", str(out)]) == 0

    captured = capsys.readouterr()
    assert "1 篇文档" in captured.out
    assert (out / CHUNKS_FILE).is_file()
    assert (out / MANIFEST_FILE).is_file()


def test_cli_quiet_writes_nothing_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = make_tree(tmp_path)

    assert cli.main([str(source), "-o", str(tmp_path / "out"), "--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_cli_max_chars_changes_granularity(tmp_path: Path) -> None:
    source = make_tree(tmp_path)
    default_out = tmp_path / "default"
    fine_out = tmp_path / "fine"

    assert cli.main([str(source), "-o", str(default_out)]) == 0
    assert cli.main([str(source), "-o", str(fine_out), "--max-chars", "120"]) == 0

    assert chunk_count(fine_out) > chunk_count(default_out)
    assert chunk_count(default_out) >= 1


def test_cli_pattern_option(tmp_path: Path) -> None:
    source = make_tree(tmp_path)
    (source / "page.mdx").write_text(DOC, encoding="utf-8")
    out = tmp_path / "out"

    assert cli.main([str(source), "-o", str(out), "-p", "*.mdx"]) == 0

    lines = (out / CHUNKS_FILE).read_text(encoding="utf-8").splitlines()
    assert lines
    assert all('"page.mdx"' in line for line in lines)


def test_cli_missing_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(tmp_path / "missing"), "-o", str(tmp_path / "out")]) == 2
    assert "源目录不存在" in capsys.readouterr().err


def test_cli_invalid_sizes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = make_tree(tmp_path)

    assert cli.main([str(source), "-o", str(tmp_path / "out"), "--max-chars", "0"]) == 2
    assert "错误" in capsys.readouterr().err


def test_cli_verify_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = make_tree(tmp_path)

    assert cli.main([str(source), "-o", str(tmp_path / "out"), "--verify"]) == 0
    assert capsys.readouterr().err == ""


def test_cli_verify_failure_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_tree(tmp_path)
    monkeypatch.setattr(cli, "verify_chunks", lambda chunks, root: ["boom"])

    assert cli.main([str(source), "-o", str(tmp_path / "out"), "--verify"]) == 1
    assert "boom" in capsys.readouterr().err
    assert not (tmp_path / "out" / CHUNKS_FILE).exists()
