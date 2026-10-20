# splitter —— 分节与打包

把 [blocks.md](blocks.md) 产出的块按标题层级分组，并在每组内打包成不超过 `max_chars` 的偏移区间。
这一层只关心“切哪里”，不知道文档路径，也不生成 `text`。

## 导入

```python
from langchain_md_chunker import RawChunk, split_text
```

## `split_text`

```python
def split_text(text: str, config: ChunkConfig | None = None) -> list[RawChunk]
```

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `text` | `str` | 文档全文 |
| `config` | `ChunkConfig \| None` | 为 `None` 时使用 `ChunkConfig()`（**通用默认**：不丢弃任何语料样板） |

返回按位置升序、互不重叠的 `RawChunk` 列表；空白文本返回 `[]`。

```python
from langchain_md_chunker import split_text

split_text("# T\n\nbody\n")
# [RawChunk(start=0, end=9, start_line=1, end_line=3,
#           context='T', headings_with_levels=((1, 'T'),),
#           starts_with_heading=True)]
```

### 打包规则

1. **按标题分节**：维护标题栈，每个块归属唯一一节；`###` 的子节不会混进父节的 chunk。
2. **贪心打包**：同节内按块累积到 `max_chars`，超出才断开；标题行总是与正文首块同行（即使正文是单个超大块）。
3. **超长块**：单个块超过上限时按行拆，断点优先级为
   子元素起始行（`<Tab>`、`<Step>` 等）→ 空行 → 任意行。
4. **跳过块即硬断点**：`skip_kinds` / `skip_prefixes` 命中的块不产出内容，并强制断开前后 chunk。
5. **孤立标题不产出**：只有标题、没有正文的节会被丢弃（其标题仍作为子节的上下文）。

## `RawChunk`

```python
@dataclass(frozen=True, slots=True)
class RawChunk:
    start: int
    end: int
    start_line: int
    end_line: int
    context: str
    headings_with_levels: tuple[tuple[int, str], ...] = ()
    starts_with_heading: bool = False
```

与 `Chunk` 的区别：没有 `doc`、`id`、`text`、`content`，因为这一层不绑定文档。

| 字段 | 说明 |
| --- | --- |
| `start` / `end` | 半开区间字符偏移 |
| `start_line` / `end_line` | 1-based 闭区间行号 |
| `context` | 标题路径，如 `A > B` |
| `headings_with_levels` | 带原始层级的标题路径，如 `((1, "A"), (2, "B"))`；层级可能跳级 |
| `starts_with_heading` | 该区间是否已以本节标题行开头（决定是否还要补标题前缀） |

### `headings`

```python
@property
def headings(self) -> tuple[str, ...]
```

由 `headings_with_levels` 派生，只保留标题文本：

```python
raw.headings  # ("A", "B")
```

## 与 `Chunk` 的关系

```python
from langchain_md_chunker import Chunker

chunks = Chunker().split_text("# T\n\nbody\n")
chunks[0].text    == "# T\n\nbody"   # chunker 按偏移切片
chunks[0].content == "# T\n\nbody"   # 未开启 include_headings
```

`Chunker` 负责绑定 `doc`/`id`、切片出 `text`，并在 `include_headings=True` 时生成 `content`。

## 另见

- 解析规则：[blocks.md](blocks.md)
- 配置项：[config.md](config.md)
- 完整对象：[models.md](models.md)
