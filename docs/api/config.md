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
    min_chars: int = 0
    merge_small_sections: bool = True
    id_strategy: str = "location"
```

不可变配置对象，可以在多个 `Chunker` 之间共享。

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `max_chars` | `int` | `1500` | 单个 chunk 的软上限（按**原文**字符数）。超长块会按行切分；只有单行本身超过上限、或为避免尾部分隔符单独成块时，才可能少量超限。 |
| `skip_kinds` | `tuple[str, ...]` | `("frontmatter", "export", "import", "comment")` | 不产出 chunk 的块类型。跳过块会同时成为**硬断点**，不会混进相邻 chunk。 |
| `skip_prefixes` | `tuple[str, ...]` | `()` | 块文本（去掉前导空白）以这些前缀开头时视为样板丢弃。默认空：核心不内置任何语料特征。 |
| `include_headings` | `bool` | `False` | 为 `True` 时，`Chunk.content` 会加上所在标题路径（`# A` / `## B` / `### C`）；`Chunk.text`、偏移、行号不受影响。 |
| `min_chars` | `int` | `0` | 大于 0 时，同一父节下、同一层级的相邻小节若小于该长度就合并（合并后仍须不超过 `max_chars`）。`0` 关闭合并。合并后的 chunk 使用**第一个**小节的标题路径，正文中仍保留后续小节标题。 |
| `merge_small_sections` | `bool` | `True` | 设为 `False` 可保留小节边界，即使设置了 `min_chars`。 |
| `id_strategy` | `str` | `"location"` | `"location"` 用文档路径 + 偏移生成 id；`"content"` 用 `Chunk.content` 生成，内容相同的 chunk 共享 id。两者都是 `c` + 16 位十六进制。 |

### 校验

构造时执行，失败抛 `ValueError`：

| 条件 | 消息 |
| --- | --- |
| `max_chars <= 0` | `max_chars must be positive` |
| `min_chars` 不在 `0..max_chars` 内 | `min_chars must be between 0 and max_chars` |
| `skip_prefixes` 中存在空白项 | `skip_prefixes must not contain blank prefixes` |
| `id_strategy` 不属于 `ID_STRATEGIES` | `id_strategy must be one of (...)` |

### 示例

```python
from langchain_md_chunker import ChunkConfig

config = ChunkConfig(max_chars=800, include_headings=True)
config = ChunkConfig(skip_prefixes=("> ## Generated banner",))
config = ChunkConfig(min_chars=200)                      # 合并小兄弟小节
config = ChunkConfig(id_strategy="content")              # 内容寻址 id
```

语料相关的样板建议用预设表达（[presets.md](presets.md)），不要写进库默认值：

```python
from langchain_md_chunker import langchain_docs

config = langchain_docs(max_chars=1200, include_headings=True)
```

## `DEFAULT_SKIP_KINDS`

```python
DEFAULT_SKIP_KINDS: tuple[str, ...] = ("frontmatter", "export", "import", "comment")
```

与语料无关、默认跳过的块类型：

- `frontmatter`：文档开头的 YAML 块（仅当文件以 `---` 开始且能找到结束行）。
- `export`：文档内联的 JS 辅助代码（`export const ...`），按大括号配平整段跳过。
- `import`：MDX 顶部的 `import ...` 语句。
- `comment`：MDX 注释块 `{/* ... */}`。

## `ID_STRATEGIES`

```python
ID_STRATEGIES: tuple[str, ...] = ("location", "content")
```

`ChunkConfig.id_strategy` 的合法取值：

- `location`：`sha1(doc, start, end)` 前 16 位。切片位置不变则 id 稳定，适合增量索引。
- `content`：`sha1(content)` 前 16 位。内容相同即 id 相同，可用于跨文档去重；不同位置但内容一致的 chunk 会共享 id。

## 另见

- 语料预设：[presets.md](presets.md)
- 块类型由内部解析层识别（`frontmatter`、`export` 等），不属于公开 API。
