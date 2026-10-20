# integrations —— 下游框架适配

可选适配器。核心包**不依赖**任何框架：适配函数在被调用时才导入目标库，没装也不影响其他功能。

## 导入

```python
from langchain_md_chunker import to_langchain_documents
```

## `to_langchain_documents`

```python
def to_langchain_documents(
    chunks: Iterable[Chunk],
    *,
    page_content: Literal["content", "text"] = "content",
) -> list[Any]
```

把 `Chunk` 转成 `langchain_core.documents.Document`。

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `chunks` | `Iterable[Chunk]` | — | `Chunker` 产出或 `read_chunks` 读回的 chunk |
| `page_content` | `"content" \| "text"` | `"content"` | 用哪个字段作为文档正文：`content` 可带标题前缀，`text` 是原文精确切片 |

### 依赖

```bash
uv add langchain-core        # 或 pip install langchain-core
```

未安装时调用会抛 `ImportError`，消息中给出安装命令：

```text
ImportError: to_langchain_documents() requires langchain-core; install it with `pip install langchain-core`
```

### 元数据

每个 `Document.metadata` 包含：

| 键 | 说明 |
| --- | --- |
| `id` | chunk 的稳定 ID |
| `source` | 源文件路径（`chunk.doc` 的别名，符合 LangChain 习惯） |
| `doc` | 源文件路径 |
| `start` / `end` | 半开区间字符偏移（Unicode 码点） |
| `start_line` / `end_line` | 1-based 行号 |
| `chars` | 原文切片长度 |
| `headings` | 标题路径（`list[str]`） |
| `context` | 标题路径字符串，如 `A > B` |

### 示例

```python
from langchain_md_chunker import Chunker, langchain_docs, to_langchain_documents

chunks = Chunker(langchain_docs()).split_directory("data/langchain-docs")
documents = to_langchain_documents(chunks)

print(documents[0].page_content[:40])
print(documents[0].metadata["source"], documents[0].metadata["start"])
```

需要精确原文而不是标题前缀时：

```python
documents = to_langchain_documents(chunks, page_content="text")
```

### 异常

| 场景 | 异常 |
| --- | --- |
| `page_content` 不是 `"content"` / `"text"` | `ValueError` |
| 未安装 `langchain-core` | `ImportError`（含安装提示） |

## 另见

- 输出模型：[models.md](models.md)
- 读取本地索引：[storage.md](storage.md)
