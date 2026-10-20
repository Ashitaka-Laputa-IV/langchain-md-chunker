# chunker —— 文件与目录编排

面向使用者的高层入口：遍历文件、绑定文档路径、切片生成 `Chunk`。内部依次经过解析层与切分层，
这两层属于实现细节，不在公开 API 范围内。

## 导入

```python
from langchain_md_chunker import DEFAULT_PATTERNS, Chunker
from langchain_md_chunker.chunker import IGNORED_DIRS
```

## `DEFAULT_PATTERNS`

```python
DEFAULT_PATTERNS: tuple[str, ...] = ("*.md", "*.mdx", "*.MD", "*.MDX")
```

`split_directory` 默认匹配的文件模式。

## `IGNORED_DIRS`

```python
IGNORED_DIRS: frozenset[str] = frozenset({".git", ".venv", "node_modules", "build", "dist", ...})
```

`split_directory` 递归时不会进入这些目录（版本控制、虚拟环境、依赖与缓存目录），避免把仓库根目录当语料时误伤。

## `Chunker`

```python
class Chunker:
    def __init__(self, config: ChunkConfig | None = None) -> None
```

| 参数 | 说明 |
| --- | --- |
| `config` | 为 `None` 时使用 `ChunkConfig()`（通用默认，不丢弃语料样板）。语料专属规则用 [presets.md](presets.md) 显式传入。 |

实例无状态（除配置外），可复用。

### `split_text`

```python
def split_text(self, text: str, *, doc: str = "<memory>") -> list[Chunk]
```

切分内存中的文本。

| 参数 | 说明 |
| --- | --- |
| `text` | 文档全文 |
| `doc` | 写入每个 `Chunk.doc` 的标识，默认 `"<memory>"`；不影响偏移 |

```python
from langchain_md_chunker import Chunker

chunks = Chunker().split_text("# T\n\nbody\n", doc="page.md")
assert chunks[0].doc == "page.md"
```

### `split_file`

```python
def split_file(self, path: str | Path, *, root: str | Path | None = None) -> list[Chunk]
```

读取一个 UTF-8 文件并切分。

| 参数 | 说明 |
| --- | --- |
| `path` | 文件路径 |
| `root` | `Chunk.doc` 的基准目录；默认取文件所在目录。文件不在 `root` 内时 `doc` 回退为文件名 |

```python
chunks = Chunker().split_file("data/langchain-docs/oss/python/learn.md", root="data/langchain-docs")
chunks[0].doc   # "oss/python/learn.md"
```

可能抛出：`FileNotFoundError`（文件不存在）、`IsADirectoryError`（传了目录）、
`UnicodeDecodeError`（不是 UTF-8）。

### `split_directory`

```python
def split_directory(
    self,
    root: str | Path,
    patterns: Sequence[str] = DEFAULT_PATTERNS,
) -> list[Chunk]
```

递归切分目录下所有匹配文件。

| 参数 | 说明 |
| --- | --- |
| `root` | 源目录；不存在或不是目录时抛 `NotADirectoryError` |
| `patterns` | glob 模式序列，可重复；同一文件只会被切分一次 |

遍历时会跳过 `IGNORED_DIRS`（`.git`、`.venv`、`node_modules` 等）；默认模式同时覆盖小写与大写后缀（`*.md` / `*.MD`）。

- 文件按 `path.as_posix()` 排序，输出顺序跨平台稳定；
- 空目录 / 无匹配返回 `[]`；
- 每个文件的 `doc` 是相对于 `root` 的 POSIX 路径。

```python
from langchain_md_chunker import Chunker, langchain_docs

chunker = Chunker(langchain_docs())
chunks = chunker.split_directory("data/langchain-docs")
chunks = chunker.split_directory("data/langchain-docs", patterns=("*.md",))
```

## 完整示例

```python
from pathlib import Path

from langchain_md_chunker import Chunker

path = Path("data/langchain-docs/oss/python/learn.md")
chunks = Chunker().split_file(path)
source = path.read_text(encoding="utf-8")

assert all(source[c.start : c.end] == c.text for c in chunks)
```

## 另见

- 配置与预设：[config.md](config.md)、[presets.md](presets.md)
- 偏移校验：[verify.md](verify.md)
- 落盘：[storage.md](storage.md)
