# API 参考

`langchain-md-chunker` v0.1.0。把 markdown / MDX 文档切成带**源文件字符偏移**的 chunk，并可持久化为 JSONL。

本文档是纯 Markdown，可直接在 GitHub / 编辑器里阅读，不依赖文档构建工具。

## 安装与导入

```bash
uv add langchain-md-chunker       # 或 uv sync（仓库开发）
```

```python
from langchain_md_chunker import Chunker, ChunkConfig, Chunk, langchain_docs
```

包没有运行时第三方依赖，核心实现只用标准库。

## 模块地图

| 模块 | 职责 | 文档 |
| --- | --- | --- |
| `langchain_md_chunker.blocks` | 行 → `Block`：识别标题、围栏代码、表格、引用、MDX 组件、列表、段落、分隔线、frontmatter、JS export | [blocks.md](blocks.md) |
| `langchain_md_chunker.splitter` | `Block` → 标题分节 → 打包 → `RawChunk`（只产出偏移区间） | [splitter.md](splitter.md) |
| `langchain_md_chunker.chunker` | 文件 / 目录遍历、绑定 `doc`/`id`、装配 `Chunk` | [chunker.md](chunker.md) |
| `langchain_md_chunker.models` | 输出模型 `Chunk` | [models.md](models.md) |
| `langchain_md_chunker.config` | `ChunkConfig`（与语料无关的默认值） | [config.md](config.md) |
| `langchain_md_chunker.presets` | 语料预设（`langchain_docs`） | [presets.md](presets.md) |
| `langchain_md_chunker.storage` | JSONL + manifest 读写、统计 | [storage.md](storage.md) |
| `langchain_md_chunker.verify` | 回读源文件校验偏移 | [verify.md](verify.md) |
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

## 公开面与稳定性

- **稳定面**：`langchain_md_chunker.__all__` 中的名字，以及各模块 `__all__` 中的名字（本文档逐页列出）。
  当前导出：`CHUNKS_FILE`、`DEFAULT_PATTERNS`、`MANIFEST_FILE`、`Block`、`Chunk`、`ChunkConfig`、
  `Chunker`、`Line`、`RawChunk`、`__version__`、`build_manifest`、`langchain_docs`、`parse_blocks`、
  `read_chunks`、`read_manifest`、`split_text`、`verify_chunks`、`write_chunks`。
- **内部实现**：以 `_` 开头的名字（如 `_build_units`、`_find_mdx_close`）不属于公开面，可能随时调整。
- 版本遵循语义化版本；`0.x` 期间允许次版本号引入破坏性变更，变更会记录在提交与 README 中。

## 三条不变量

1. **切片精确**：`source[start:end] == chunk.text` 永远成立，切分只挑断点，不改写文本。
2. **偏移单位是码点**：`start`/`end` 是解码后 Python `str` 的下标（Unicode 码点），不是 UTF-8 字节；
   JavaScript 需先 `Array.from(text)` 再切片。
3. **行号 1-based、闭区间**：`start_line`/`end_line` 指向 `text` 在源文件中的行范围。

`Chunk.content` 是唯一可能不等于 `text` 的字段：开启 `include_headings` 后会加上标题路径，详见
[models.md](models.md) 与 [config.md](config.md)。

## 另见

- 项目总览与命令行用法：[../README.md](../../README.md)
- 分层与扩展点：[../ARCHITECTURE.md](../../ARCHITECTURE.md)
