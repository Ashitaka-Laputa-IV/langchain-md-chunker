"""文档一致性：公开 API 必须出现在 docs/api，内部链接必须可解析。"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType

import pytest

import langchain_md_chunker
from langchain_md_chunker import chunker, cli, config, models, presets, storage, verify

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs" / "api"

MODULES: dict[str, ModuleType] = {
    "chunker": chunker,
    "cli": cli,
    "config": config,
    "models": models,
    "presets": presets,
    "storage": storage,
    "verify": verify,
}


def docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(DOCS_DIR.glob("*.md")))


def test_docs_directory_exists() -> None:
    assert (DOCS_DIR / "index.md").is_file()


@pytest.mark.parametrize("name", sorted(langchain_md_chunker.__all__))
def test_root_api_is_documented(name: str) -> None:
    assert f"`{name}`" in docs_text(), f"{name} 未出现在 docs/api"


@pytest.mark.parametrize("module_name", sorted(MODULES))
def test_module_api_is_documented(module_name: str) -> None:
    for name in MODULES[module_name].__all__:
        assert f"`{name}`" in docs_text(), f"{module_name}.{name} 未出现在 docs/api"


def test_internal_links_resolve() -> None:
    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)#]+\.md)\)", text):
            resolved = (path.parent / target).resolve()
            assert resolved.is_file(), f"{path.name} -> {target} 不存在"
