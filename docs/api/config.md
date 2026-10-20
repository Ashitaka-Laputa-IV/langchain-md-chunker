# config —— 切分配置

## 导入

```python
from langchain_md_chunker import ChunkConfig
from langchain_md_chunker.config import DEFAULT_SKIP_KINDS
```

## `ChunkConfig`

```python
@dataclass(frozen=True, slots=True)
class ChunkConfig:
    max_chars: int = 1500
    skip_kinds: tuple[str, ...] = DEFAULT_SKIP_KINDS
    skip_prefixes: tuple[str, ...] = ()
    include_headings: bool = False
```

不可变配置对象，可以在多个 `Chunker` 之间共享。

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `max_chars` | `int` | `1500` | 单个 chunk 的软上限（按**原文**字符数）。只有不可拆的原子块（单个代码围栏、表格、巨型组件、超长单行）允许超限。 |
| `skip_kinds` | `tuple[str, ...]` | `("frontmatter", "export")` | 不产出 chunk 的块类型。跳过块会同时成为**硬断点**，不会混进相邻 chunk。 |
| `skip_prefixes` | `tuple[str, ...]` | `()` | 块文本（去掉前导空白）以这些前缀开头时视为样板丢弃。默认空：核心不内置任何语料特征。 |
| `include_headings` | `bool` | `False` | 为 `True` 时，`Chunk.content` 会加上所在标题路径（`# A` / `## B` / `### C`）；`Chunk.text`、偏移、行号不受影响。 |

### 校验

构造时执行，失败抛 `ValueError`：

| 条件 | 消息 |
| --- | --- |
| `max_chars <= 0` | `max_chars must be positive` |
| `skip_prefixes` 中存在空白项 | `skip_prefixes must not contain blank prefixes` |

### 示例

```python
from langchain_md_chunker import ChunkConfig

config = ChunkConfig(max_chars=800, include_headings=True)
config = ChunkConfig(skip_prefixes=("> ## Generated banner",))
```

语料相关的样板建议用预设表达（[presets.md](presets.md)），不要写进库默认值：

```python
from langchain_md_chunker import langchain_docs

config = langchain_docs(max_chars=1200, include_headings=True)
```

## `DEFAULT_SKIP_KINDS`

```python
DEFAULT_SKIP_KINDS: tuple[str, ...] = ("frontmatter", "export")
```

与语料无关、默认跳过的块类型：

- `frontmatter`：文档开头的 YAML 块（仅当文件以 `---` 开始且能找到结束行）。
- `export`：文档内联的 JS 辅助代码（`export const ...`），按大括号配平整段跳过。

## 另见

- 语料预设：[presets.md](presets.md)
- 块类型由内部解析层识别（`frontmatter`、`export` 等），不属于公开 API。
