"""发布前元数据检查：版本、入口点、类型标记与 PyPI 可渲染性。"""

from __future__ import annotations

import re
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

import langchain_md_chunker

ROOT = Path(__file__).resolve().parents[1]


def read_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_version_matches_pyproject() -> None:
    assert read_pyproject()["project"]["version"] == langchain_md_chunker.__version__


def test_installed_metadata_matches_version() -> None:
    try:
        installed = metadata.version("langchain-md-chunker")
    except metadata.PackageNotFoundError:
        pytest.skip("包未安装到当前环境")
    assert installed == langchain_md_chunker.__version__


def test_console_scripts_are_declared() -> None:
    scripts = read_pyproject()["project"]["scripts"]
    assert scripts["chunk"] == "langchain_md_chunker.cli:main"
    assert scripts["langchain-md-chunker"] == "langchain_md_chunker.cli:main"

    entry_points = metadata.entry_points(group="console_scripts")
    installed = {point.name for point in entry_points if point.dist.name == "langchain-md-chunker"}
    if installed:
        assert {"chunk", "langchain-md-chunker"} <= installed


def test_typed_marker_exists() -> None:
    assert (ROOT / "src" / "langchain_md_chunker" / "py.typed").is_file()


def test_readme_uses_absolute_links() -> None:
    # PyPI 会把相对链接解析到 pypi.org 下，必须使用绝对 URL。
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", text):
        without_anchor = target.split("#", 1)[0]
        if not without_anchor:
            continue
        assert without_anchor.startswith(("https://", "http://", "mailto:")), (
            f"README 中存在相对链接，PyPI 上会失效: {target}"
        )


def test_packaged_readme_is_readme_md() -> None:
    assert read_pyproject()["project"]["readme"] == "README.md"
