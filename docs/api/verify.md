# verify —— 偏移一致性校验

回读源文件，逐条确认 `chunk.text` 与 `source[start:end]` 一致。用于 CI、发布前检查，或排查“索引与源文件
不同步”的问题。

## 导入

```python
from langchain_md_chunker import verify_chunks
```

## `verify_chunks`

```python
def verify_chunks(chunks: Iterable[Chunk], root: str | Path) -> list[str]
```

| 参数 | 说明 |
| --- | --- |
| `chunks` | 待校验的 chunk 序列，通常来自 `Chunker` 或 `read_chunks` |
| `root` | 源文档根目录；每个 `chunk.doc` 相对它解析 |

返回问题描述列表；**空列表表示全部一致**。函数不抛异常：源文件不可读也会被收集为问题。

```python
from langchain_md_chunker import verify_chunks

problems = verify_chunks(chunks, "data/langchain-docs")
if problems:
    for problem in problems:
        print(problem)
```

### 问题消息

| 场景 | 消息 |
| --- | --- |
| 文件缺失或不是 UTF-8 | `<doc>: cannot read source file (<异常类型>)` |
| 偏移越界或区间非法 | `<id> <doc>: offsets out of range` |
| 切片内容不符 | `<id> <doc>@<start>:<end>: slice mismatch` |

同一文档读取失败只报告一次，后续 chunk 不再重复读取。消息为英文，便于与 CLI 输出保持一致。

### 校验内容

- `0 <= start < end <= len(source)`；
- `source[start:end] == chunk.text`。

它**不校验** `content`（可能含标题前缀）、`headings`、行号或 ID；这些由解析/切分测试覆盖。

## CLI

```bash
uv run chunk data/langchain-docs --verify
```

校验失败时打印每条问题并以退出码 `1` 结束，写入磁盘前即中止。详见 [cli.md](cli.md)。
