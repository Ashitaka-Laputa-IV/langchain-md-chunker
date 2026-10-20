# storage —— JSONL 与 manifest

把 `Chunk` 持久化到本地目录，并生成一份可复现的清单（`manifest.json`）。不使用数据库，方便直接查看、
流式读取或作为 RAG 语料加载。

## 导入

```python
from langchain_md_chunker import (
    CHUNKS_FILE,
    MANIFEST_FILE,
    build_manifest,
    read_chunks,
    read_manifest,
    write_chunks,
)
```

## 常量

| 名称 | 值 | 说明 |
| --- | --- | --- |
| `CHUNKS_FILE` | `"chunks.jsonl"` | chunk 数据文件 |
| `MANIFEST_FILE` | `"manifest.json"` | 清单文件 |
| `FORMAT_VERSION` | `1` | 清单中的格式版本（`langchain_md_chunker.storage`） |

## 目录布局

```
<out_dir>/
├── chunks.jsonl    # 每行一个 Chunk，源文件顺序
└── manifest.json   # 源目录、配置、统计
```

## `write_chunks`

```python
def write_chunks(
    chunks: Iterable[Chunk],
    out_dir: str | Path,
    *,
    manifest: dict[str, Any] | None = None,
) -> tuple[Path, Path]
```

| 参数 | 说明 |
| --- | --- |
| `chunks` | 可迭代的 `Chunk`；逐条序列化，不会整体驻留内存 |
| `out_dir` | 输出目录，不存在时自动创建 |
| `manifest` | 非 `None` 时写入 `manifest.json` |

返回 `(chunks.jsonl 路径, manifest.json 路径)`。

**写入方式**：每个文件先写同目录临时文件（`.<name>.*.tmp`）再 `os.replace` 原子替换，因此读取方不会看到
截断的文件。两个文件分别替换，**不是跨文件事务**：极端情况下读者可能短暂看到“新 chunk + 旧 manifest”。

```python
from langchain_md_chunker import build_manifest, write_chunks

config = langchain_docs()
manifest = build_manifest(chunks, source_root="data/langchain-docs", config=config)
chunks_path, manifest_path = write_chunks(chunks, "data/chunks", manifest=manifest)
```

## `read_chunks`

```python
def read_chunks(path: str | Path) -> list[Chunk]
```

| 参数 | 说明 |
| --- | --- |
| `path` | 目录时读取其中的 `chunks.jsonl`；也可直接传 `.jsonl` 文件路径 |

空行被忽略；每行必须是合法 JSON 对象（`Chunk.from_dict` 的输入）。文件损坏时抛 `json.JSONDecodeError`，
文件不存在时抛 `FileNotFoundError`。

## `read_manifest`

```python
def read_manifest(out_dir: str | Path) -> dict[str, Any]
```

读取 `<out_dir>/manifest.json`；文件不存在时返回 `{}`。内容损坏时抛 `json.JSONDecodeError`。

## `build_manifest`

```python
def build_manifest(
    chunks: Sequence[Chunk],
    *,
    source_root: str | Path,
    config: ChunkConfig,
) -> dict[str, Any]
```

生成清单字典，不写盘（写盘由 `write_chunks` 负责）。

| 字段 | 说明 |
| --- | --- |
| `format_version` | 当前为 `1` |
| `generated_at` | UTC 时间戳（秒级），仅用于排查；设置 `SOURCE_DATE_EPOCH` 时使用该时间，便于可复现构建 |
| `source_root` | 源目录；在当前工作目录内时写相对路径（跨机器可复现，不泄露本地绝对路径） |
| `package_version` | 生成该索引的 `langchain-md-chunker` 版本 |
| `config.max_chars` | 切分上限 |
| `config.skip_kinds` | 丢弃的块类型 |
| `config.skip_prefixes` | 丢弃的样板前缀 |
| `config.include_headings` | 是否把标题写入 `content` |
| `config.min_chars` | 小节合并阈值（`0` 表示关闭） |
| `config.merge_small_sections` | 是否允许合并小兄弟小节 |
| `config.id_strategy` | `location` 或 `content` |
| `doc_count` | 文档数 |
| `chunk_count` | chunk 总数 |
| `total_chars` | 所有 chunk 的原文长度之和 |
| `chunk_chars_min` / `chunk_chars_avg` / `chunk_chars_max` | 原文长度统计（空集时为 `0`） |

## `chunks.jsonl` 记录

每行是 `Chunk.to_dict()`：

```json
{
  "id": "c32352242f276a1b",
  "doc": "oss/python/concepts/context.md",
  "start": 181,
  "end": 1541,
  "start_line": 5,
  "end_line": 27,
  "chars": 1360,
  "headings": ["Context overview", "Context engineering"],
  "context": "Context overview > Context engineering",
  "text": "## Context engineering\n\n...",
  "content": "# Context overview\n\n## Context engineering\n\n...",
  "kind": "mixed",
  "lang": ""
}
```

字段含义见 [models.md](models.md)。`content` 可能含合成内容（标题、补出的围栏、重复表头、MDX 注释），
回原文定位请用 `text` 与 `start/end`。

## 读取示例

```python
from langchain_md_chunker import read_chunks, read_manifest

chunks = read_chunks("data/chunks")
manifest = read_manifest("data/chunks")
print(len(chunks), manifest["chunk_count"], manifest["config"]["max_chars"])
```
