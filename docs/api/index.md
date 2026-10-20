# API 参考

`langchain-md-chunker` v0.4.2。把 markdown / MDX 文档切成带**源文件字符偏移**的 chunk，并可持久化为 JSONL。

本文档只覆盖**公开 API**；内部实现不在兼容性承诺内。纯 Markdown，可直接在 GitHub / 编辑器里阅读。

## 安装与导入

```bash
uv add langchain-md-chunker       # 或 uv sync（仓库开发）
```

```python
from langchain_md_chunker import Chunker, ChunkConfig, Chunk, langchain_docs
```

包没有运行时第三方依赖，核心实现只用标准库。

## 公开模块

| 模块 | 职责 | 文档 |
| --- | --- | --- |
| `langchain_md_chunker.chunker` | 文件 / 目录遍历、绑定 `doc`/`id`、生成 `Chunk` | [chunker.md](chunker.md) |
| `langchain_md_chunker.config` | `ChunkConfig`（与语料无关的默认值） | [config.md](config.md) |
| `langchain_md_chunker.presets` | 语料预设（`langchain_docs`） | [presets.md](presets.md) |
| `langchain_md_chunker.models` | 输出模型 `Chunk` | [models.md](models.md) |
| `langchain_md_chunker.storage` | JSONL + manifest 读写、统计 | [storage.md](storage.md) |
| `langchain_md_chunker.verify` | 回读源文件校验偏移 | [verify.md](verify.md) |
| `langchain_md_chunker.integrations` | 可选适配器（LangChain `Document`） | [integrations.md](integrations.md) |
| `langchain_md_chunker.cli` | 命令行 `uv run chunk` | [cli.md](cli.md) |

## 三个常见任务

切目录并落盘：

```python
from langchain_md_chunker import Chunker, build_manifest, langchain_docs, write_chunks

config = langchain_docs(max_chars=1200)
chunks = Chunker(config).split_directory("data/langchain-docs")
manifest = build_manifest(chunks, source_root="data/langchain-docs", config=config)
write_chunks(chunks, "data/chunks", manifest=manifest)
```

只要内存里的 chunk：

```python
from langchain_md_chunker import Chunker

chunks = Chunker().split_text("# Title\n\nBody text.\n")
print(chunks[0].headings, chunks[0].text, chunks[0].content)
```

回读并校验偏移：

```python
from langchain_md_chunker import read_chunks, verify_chunks

chunks = read_chunks("data/chunks")
problems = verify_chunks(chunks, "data/langchain-docs")   # [] 表示全部一致
```

## 公开面

**稳定面**就是 `langchain_md_chunker.__all__`：

```text
CHUNKS_FILE  DEFAULT_PATTERNS  MANIFEST_FILE  Chunk  ChunkConfig  Chunker
__version__  build_manifest  langchain_docs  read_chunks  read_manifest
to_langchain_documents  verify_chunks  write_chunks
```

其中 `__version__` 是包版本号（当前 `0.4.2`）。

- `Chunker` 是唯一入口，`split_text` / `split_file` / `split_directory` / `iter_directory` 覆盖内存、单文件、目录（列表或流式）。
- 配置、预设、模型、存储、校验、CLI 的公开名字见各页顶部的 `__all__` 说明。
- 以 `_` 开头的名字（如 `_build_units`、`_find_mdx_close`）属于内部实现，可能随时调整。

### 内部实现（非公开）

以下模块是实现细节，**不属于公开 API**，不保证兼容性，也不在本文档范围内：

| 模块 | 说明 |
| --- | --- |
| `langchain_md_chunker.blocks` | 行 → `Block` 解析（围栏、表格、MDX、export 配平等） |
| `langchain_md_chunker.splitter` | 标题分节、打包、超长块拆分，产出 `RawChunk` |

需要这些层的能力时，优先用 `Chunker`；确有必要可直接导入，但请锁定版本。

## 三条不变量

1. **切片精确**：`source[start:end] == chunk.text` 永远成立，切分只挑断点，不改写文本。
2. **偏移单位是码点**：`start`/`end` 是解码后 Python `str` 的下标（Unicode 码点），不是 UTF-8 字节；
   JavaScript 需先 `Array.from(text)` 再切片。
3. **行号 1-based、闭区间**：`start_line`/`end_line` 指向 `text` 在源文件中的行范围。

`Chunk.content` 是唯一可能不等于 `text` 的字段：它可能加上标题路径（`include_headings`）以及
分片包装（补出的围栏、重复表头、MDX 组件注释）。回原文定位请始终使用 `text` 与 `start/end`，
详见 [models.md](models.md) 与 [config.md](config.md)。

## 另见

- 项目总览与命令行用法：[../../README.md](../../README.md)
- 分层与扩展点：[../../ARCHITECTURE.md](../../ARCHITECTURE.md)
