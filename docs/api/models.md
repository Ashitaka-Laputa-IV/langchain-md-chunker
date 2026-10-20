# models —— 输出模型

## 导入

```python
from langchain_md_chunker import Chunk
```

## `Chunk`

```python
@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    doc: str
    start: int
    end: int
    start_line: int
    end_line: int
    headings: tuple[str, ...]
    context: str
    text: str
    content: str = ""
    kind: str = "text"
    lang: str = ""
```

单个 chunk 的完整描述。不可变（`frozen=True`），可安全地跨线程/缓存传递。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `str` | 稳定 ID：`c` + 16 位十六进制，如 `c80da3f281601b31`。默认由 `sha1(doc + start + end + content)` 派生；`id_strategy="content"` 时只由 `content` 派生。 |
| `doc` | `str` | 相对 `root` 的源文件路径（POSIX 分隔符），如 `oss/python/learn.md`；`split_text` 默认 `"<memory>"`。 |
| `start` / `end` | `int` | 半开区间 `[start, end)`，单位是 Unicode 码点。 |
| `start_line` / `end_line` | `int` | 1-based、闭区间的源文件行号。 |
| `headings` | `tuple[str, ...]` | 由外到内的标题文本，如 `("LangChain", "Agents")`。 |
| `context` | `str` | `headings` 用 ` > ` 连接，可直接拼到 embedding 输入前。 |
| `text` | `str` | 原文切片，逐字符等于 `source[start:end]`。 |
| `content` | `str` | 供 embedding / 展示使用：`text` 加上标题路径（`include_headings`）与分片包装（必要时）。包装包括补出的代码围栏、重复的表头、MDX 组件名注释。 |
| `kind` | `str` | 主导块类型：`para` / `code` / `table` / `list` / `quote` / `mdx` / `math` / `container` / `footnote`；跨多种块时为 `mixed`，只有标题时为 `text`。 |
| `lang` | `str` | chunk 全部来自同一个代码块时为其围栏语言（`python` 等），否则为空。 |

### `chars`

```python
@property
def chars(self) -> int
```

`end - start`，即原文切片长度（**不含**标题前缀、围栏、表头等合成内容）。

### `to_dict()`

```python
def to_dict(self) -> dict[str, Any]
```

返回 JSON 友好字典，键顺序固定：

```python
{
    "id": "c80da3f281601b31",
    "doc": "<memory>",
    "start": 0,
    "end": 9,
    "start_line": 1,
    "end_line": 3,
    "chars": 9,
    "headings": ["T"],
    "context": "T",
    "text": "# T\n\nbody",
    "content": "# T\n\nbody",
    "kind": "para",
    "lang": "",
}
```

### `Chunk.from_dict(data)`

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> Chunk
```

`to_dict()` 的逆操作，用于读回 JSONL：

- 必填：`id`、`doc`、`start`、`end`（`start < 0` 或 `end < start` 时抛 `ValueError`）；
- 可选：`start_line`、`end_line`（缺省 `0`）、`headings`（缺省空）、`context`、`text`、`content`、`kind`（缺省 `text`）、`lang`（缺省空）；
- `content` 缺失或为空时自动回退为 `text`。

### `content` 的归一化

构造时若 `content == ""`，会自动替换为 `text`（`__post_init__` 中完成）。因此：

```python
chunk = Chunk(id="c1", doc="a.md", start=0, end=4, start_line=1, end_line=1,
              headings=(), context="", text="body")
assert chunk.content == "body"
```

## 示例

```python
from langchain_md_chunker import Chunker

chunk = Chunker().split_text("# T\n\nbody\n")[0]
assert chunk.text == "# T\n\nbody"
assert chunk.start_line == 1 and chunk.end_line == 3
assert chunk.headings == ("T",)
assert chunk.chars == 9
```

## 另见

- 生成过程：[chunker.md](chunker.md)
- 标题前缀规则：[config.md](config.md)
