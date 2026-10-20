"""可选适配器：不安装 langchain-core 也能导入，安装后映射正确。"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from langchain_md_chunker import Chunker, to_langchain_documents


class FakeDocument:
    def __init__(self, page_content: str, metadata: dict[str, Any]) -> None:
        self.page_content = page_content
        self.metadata = metadata


@pytest.fixture()
def fake_langchain(monkeypatch: pytest.MonkeyPatch) -> None:
    core = types.ModuleType("langchain_core")
    documents = types.ModuleType("langchain_core.documents")
    documents.Document = FakeDocument  # type: ignore[attr-defined]
    core.documents = documents  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_core", core)
    monkeypatch.setitem(sys.modules, "langchain_core.documents", documents)


def test_missing_dependency_raises_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "langchain_core", None)
    monkeypatch.setitem(sys.modules, "langchain_core.documents", None)

    with pytest.raises(ImportError, match="langchain-core"):
        to_langchain_documents(Chunker().split_text("# T\n\nbody\n"))


def test_documents_use_content_and_carry_metadata(fake_langchain: None) -> None:
    chunks = Chunker().split_text("# T\n\nbody\n", doc="page.md")

    documents = to_langchain_documents(chunks)

    assert len(documents) == 1
    document = documents[0]
    assert document.page_content == "# T\n\nbody"
    assert document.metadata["source"] == "page.md"
    assert document.metadata["doc"] == "page.md"
    assert document.metadata["start"] == 0
    assert document.metadata["end"] == 9
    assert document.metadata["chars"] == 9
    assert document.metadata["headings"] == ["T"]
    assert document.metadata["context"] == "T"


def test_text_mode_uses_exact_slice(fake_langchain: None) -> None:
    chunks = Chunker().split_text("# 1\n\n## 2\n\nbody\n", doc="page.md")

    documents = to_langchain_documents(chunks, page_content="text")

    assert documents[0].page_content == chunks[0].text
    assert documents[0].page_content.startswith("## 2")


def test_invalid_page_content_is_rejected(fake_langchain: None) -> None:
    with pytest.raises(ValueError, match="page_content"):
        to_langchain_documents([], page_content="html")  # type: ignore[arg-type]
