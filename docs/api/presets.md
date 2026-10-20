# presets —— 语料预设

核心切分器不假设任何具体语料。已知文档集的特殊规则以“返回 `ChunkConfig` 的工厂函数”形式放在
`presets` 里，由调用方显式选用（CLI 默认选用 `langchain-docs`）。

## 导入

```python
from langchain_md_chunker import langchain_docs
from langchain_md_chunker.presets import LANGCHAIN_DOCS_SKIP_PREFIXES
```

## `LANGCHAIN_DOCS_SKIP_PREFIXES`

```python
LANGCHAIN_DOCS_SKIP_PREFIXES: tuple[str, ...] = (
    "> ## Documentation Index",
    '<div className="source-links">',
)
```

LangChain 官方文档每页都会出现的两块样板，没有检索价值：

- 页首的 `Documentation Index` 引用横幅；
- 页尾的 `source-links` 区块（“连接文档 / 编辑本页”链接）。

## `langchain_docs`

```python
def langchain_docs(*, max_chars: int = 1500, include_headings: bool = False) -> ChunkConfig
```

返回带 LangChain 文档样板的配置：

```python
ChunkConfig(
    max_chars=max_chars,
    skip_kinds=("frontmatter", "export"),
    skip_prefixes=LANGCHAIN_DOCS_SKIP_PREFIXES,
    include_headings=include_headings,
)
```

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `max_chars` | `int` | `1500` | 透传给 `ChunkConfig` |
| `include_headings` | `bool` | `False` | 透传给 `ChunkConfig` |

`skip_kinds` 与 `skip_prefixes` 不支持覆盖；需要自定义时直接构造 `ChunkConfig`。

```python
from langchain_md_chunker import Chunker, langchain_docs

chunks = Chunker(langchain_docs(max_chars=1000, include_headings=True)).split_directory("data/langchain-docs")
```

## 自定义预设

预设只是一个普通函数，项目内可以照此添加：

```python
from langchain_md_chunker import ChunkConfig

MY_DOCS_BOILERPLATE = (
    "> This page was generated",
    "<!-- footer -->",
)

def my_docs(*, max_chars: int = 1200) -> ChunkConfig:
    return ChunkConfig(max_chars=max_chars, skip_prefixes=MY_DOCS_BOILERPLATE)
```

## 另见

- 配置字段：[config.md](config.md)
- CLI 的 `--preset` 选项：[cli.md](cli.md)
