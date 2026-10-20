# blocks —— 文档解析层

把一篇 markdown / MDX 文本解析成扁平的 `Block` 列表。解析**不修改原文**：每个 `Block` 都是
`text[start:end]` 的精确区间。

## 导入

```python
from langchain_md_chunker import Block, Line, parse_blocks
from langchain_md_chunker.blocks import split_lines
```

## `parse_blocks`

```python
def parse_blocks(text: str) -> list[Block]
```

按行扫描，识别块类型；块之间不重叠、按位置升序。

```python
from langchain_md_chunker import parse_blocks

parse_blocks("# T\n\nbody\n")
# [
#   Block(kind='heading', start=0, end=3, level=1, title='T', lang=''),
#   Block(kind='para', start=5, end=9, level=0, title='', lang=''),
# ]
```

### 块类型

| `kind` | 识别规则 | 备注 |
| --- | --- | --- |
| `frontmatter` | 文件首行为 `---`，直到下一行 `---` / `...` | 找不到结束行则不算 frontmatter |
| `heading` | 行首 ≤3 空格 + 1~6 个 `#` + 空白 | `title` 去掉首尾空白与尾部 `###` |
| `code` | 行首 ≤3 空格 + ``` 或 ~~~ 围栏 | 闭合围栏长度 ≥ 开启长度且字符相同；未闭合则延伸到文件末尾；`lang` 取信息串第一段 |
| `table` | 行（去前导空白）以 `|` 开头 | 连续 `|` 行合并为一个块 |
| `quote` | 行（去前导空白）以 `>` 开头 | 空行后仍是 `>` 时继续同一块 |
| `list` | 行首 ≤3 空格 + `-`/`*`/`+`/`1.`/`1)` + 空白 | 到空行或下一个块起点为止 |
| `rule` | 三个及以上 `*` / `-` / `_`（可夹空格） | 单行块 |
| `mdx` | 行首列 0 的 `<Name` 组件 | 按同名标签嵌套计数闭合；围栏代码内的标签不计入；没有闭合标签时退回段落解析 |
| `export` | `export` + `default`/`const`/`let`/`var`/`function`/`async function`/`type`/`interface` | 按 `{}` 配平跨空行继续；遇到标题或围栏立即终止 |
| `para` | 其余非空行 | 到空行、标题、围栏、export 或 `<` 开头行为止 |

块会被解析出来，但**是否丢弃由切分层的 `ChunkConfig.skip_kinds` / `skip_prefixes` 决定**。

### 边界行为

- **UTF-8 BOM**：文件开头的 `\ufeff` 不参与匹配，偏移仍锚定原始文件（BOM 所在字符不属于任何块）。
- **CRLF**：行内容的 `\r` 被剥离（`Line.text` 不含 `\r`），偏移包含它，因此 `text[start:end]` 依旧精确。
- **围栏嵌套**：````md 内的 ``` 不会提前闭合外层围栏。
- **MDX 内标题 / 代码**：组件内的 `###`、围栏代码不影响块边界；围栏里的 `<Tabs>` 不会被误计为嵌套。

## `Block`

```python
@dataclass(frozen=True, slots=True)
class Block:
    kind: str
    start: int
    end: int
    level: int = 0
    title: str = ""
    lang: str = ""
```

| 字段 | 说明 |
| --- | --- |
| `kind` | 上表的块类型 |
| `start` / `end` | 半开区间字符偏移 |
| `level` | 仅 `heading` 使用：1~6 |
| `title` | 仅 `heading` 使用：标题文本 |
| `lang` | 仅 `code` 使用：围栏信息串的语言标记，可能为空 |

## `Line` 与 `split_lines`

```python
@dataclass(frozen=True, slots=True)
class Line:
    start: int
    end: int
    text: str


def split_lines(text: str) -> list[Line]
```

按 `\n` 切行并保留精确偏移，供解析与超长块拆分复用。`text` 已去掉行尾 `\r`，`end` 是行内容结束位置
（不含换行符）。文末换行会产生一个位于 `len(text)` 的空行。

```python
from langchain_md_chunker.blocks import split_lines

split_lines("a\r\nb")
# [Line(start=0, end=1, text='a'), Line(start=3, end=4, text='b')]
```

## 另见

- 如何把块打包成 chunk：[splitter.md](splitter.md)
- 跳过块配置：[config.md](config.md)
