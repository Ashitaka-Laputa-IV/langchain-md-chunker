# langchain-md-chunker

[![PyPI](https://img.shields.io/pypi/v/langchain-md-chunker.svg)](https://pypi.org/project/langchain-md-chunker/)

把 markdown / MDX 文档切成 chunk，并为每个 chunk 记录**源文件路径 + 字符偏移**，方便回溯原文。

核心是可复用的 Python 包（纯标准库、零运行时依赖）；`demo/` 里的网页只是演示，不参与打包。

> 本项目是**社区/第三方项目**，与 LangChain 官方组织没有隶属关系；包名中的 `langchain` 仅表示适用场景。

API 参考见 [docs/api/index.md](https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/blob/main/docs/api/index.md)。

## 特点

- **偏移精确**：chunk 是原文的精确切片，`source[start:end] == chunk.text` 恒成立（切分只挑断点，不改写、不拼接、不重复内容）。
- **MDX 感知**：跳过 frontmatter / `export` / `import` / MDX 注释；把 `<Tabs>`、`<CodeGroup>`、`<Accordion>`、`:::name` 容器、`$$` 公式与脚注定义当作整体；支持列表内缩进围栏，代码围栏不会被腰斩。
- **标题感知**：按标题层级分节，chunk 携带该节的标题路径（如 `LangChain > Agents > Middleware`）作为上下文。
- **标题可写入正文**（可选）：`--include-headings` 会把标题路径按原层级拼进 `content`，更适合 embedding；`text` 仍保持精确切片。
- **分片语义完整**：超长代码 / 表格 / MDX 组件被切开后，`content` 会自动补回围栏、重复表头、标注组件名，单个片段可以直接拿去 embedding。
- **可调参数**：目标长度、小节省合并、id 策略、要丢弃的块类型/样板前缀均可配置；目录读取支持指定编码与跳过坏文件。

## 快速开始

作为依赖安装（PyPI）：

```bash
uv add langchain-md-chunker

# 需要 to_langchain_documents() 时
uv add "langchain-md-chunker[langchain]"
```

仓库内开发：

```bash
uv sync                                        # 安装（含 dev 依赖）
uv run python data/download_docs.py            # 下载语料，约 180 篇 / 5 MB
uv run chunk data/langchain-docs --preset langchain-docs --verify   # 切分并校验
uv run python demo/server.py                   # 打开 http://127.0.0.1:8000 浏览
```

## 切分命令

```bash
uv run chunk <INPUT> [-o OUTPUT] [--max-chars 1500] [--preset generic|langchain-docs] \
  [--include-headings] [--min-chars 0] [--no-merge-small-sections] \
  [--id-strategy location|content] [--encoding utf-8] [--on-error raise|skip] \
  [--verify] [--quiet]
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `INPUT` | 必填 | 源文档目录或单个文件（不内置任何默认语料） |
| `-o, --output` | `data/chunks` | chunk 输出目录 |
| `--preset` | `generic` | 语料预设：`generic` 不丢样板，`langchain-docs` 丢弃 LangChain 文档每页样板 |
| `--max-chars` | `1500` | 单 chunk 目标上限（字符，针对原文） |
| `--version` | — | 打印版本号并退出 |
| `-p, --pattern` | `*.md`, `*.mdx`, `*.MD`, `*.MDX` | 文件匹配模式，可重复 |
| `--include-headings` | 关闭 | 把标题路径写进 `content`（见下节） |
| `--min-chars` | `0` | 同一父节下的小节合并阈值；`0` 关闭 |
| `--no-merge-small-sections` | 关闭 | 即使给了 `--min-chars` 也保留小节边界 |
| `--id-strategy` | `location` | `location`（路径+偏移）或 `content`（内容哈希） |
| `--encoding` | `utf-8` | 源文件读取编码 |
| `--on-error` | `raise` | `skip` 时跳过不可读 / 解码失败的文件 |
| `--verify` | 关闭 | 写盘前回读源文件，逐条校验偏移 |
| `--quiet` | 关闭 | 只输出错误与警告 |

输出：

```
data/chunks/
├── chunks.jsonl    # 每行一个 chunk，保持源文件顺序
└── manifest.json   # 源目录、配置、统计信息
```

两个文件都是“临时文件 + 原子替换”写入：切分时刷新演示页面，不会读到写了一半的索引。

`data/langchain-docs/` 与 `data/chunks/` 都在 `.gitignore` 中：语料和派生产物可随时重建，不入库。

### 语料预设

核心包本身不知道任何具体语料，默认配置**不做语料相关的丢弃**，CLI 默认也是 `--preset generic`。处理 LangChain 文档时显式启用 `langchain-docs` 预设（丢弃每页重复的索引横幅、页脚、空锚点与 `***` 分隔线）；在 Python 里同样显式选择：

```python
from langchain_md_chunker import Chunker, langchain_docs

chunker = Chunker(langchain_docs(max_chars=1200))   # 或 Chunker() 走通用默认
```

自有语料可以自己组合配置：`ChunkConfig(skip_kinds=(...), skip_prefixes=(...))`；预设只是返回 `ChunkConfig` 的工厂函数，见 `presets.py`。分层与扩展点见 [ARCHITECTURE.md](https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/blob/main/ARCHITECTURE.md)。

## 数据格式

`chunks.jsonl` 单行示例：

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

| 字段 | 说明 |
| --- | --- |
| `id` | `c` + 16 位十六进制。默认由 `doc + start + end + content` 派生（内容变化会得到新 id）；`id_strategy="content"` 时只由 `content` 派生 |
| `doc` | 相对 `manifest.source_root` 的源文件路径 |
| `start` / `end` | 半开区间 `[start, end)`，单位是 **Unicode 码点** |
| `start_line` / `end_line` | 1-based 行号，闭区间 |
| `chars` | `end - start` |
| `headings` | 标题路径（由外到内） |
| `context` | `headings` 用 ` > ` 拼接，可直接拼到 embedding 输入前 |
| `text` | 原文切片，逐字符等于 `source[start:end]` |
| `content` | 用于 embedding / 展示的文本：`text` 加上标题路径（可选）与分片包装（必要时） |
| `kind` | 主导块类型：`para` / `code` / `table` / `list` / `quote` / `mdx` / `math` / `container` / `footnote`；跨多种块时为 `mixed` |
| `lang` | 当 chunk 全部来自同一个代码块时为其围栏语言（如 `python`），否则为空 |

> `content` 中的标题、补出的围栏、重复的表头、MDX 组件注释都是**合成**的，不要拿它回原文定位；
> 回溯原文请始终使用 `text` 与 `start/end`。`id_strategy="content"` 下，内容相同的 chunk
> （例如多页共用的示例）会得到同一个 id，便于跨文档去重。

> 偏移以码点计（Python `str` 下标）。JavaScript 字符串是 UTF-16，跨码点时需
> `Array.from(text)` 后再切片——`demo/static/app.js` 已这样做。

## 标题前缀（可选）

默认关闭。开启后，每个 chunk 的 `content` 会按**原文层级**带上它所在的标题路径：

输入：

```markdown
# 1

## 2

### 3

xxxxx
```

输出（该 chunk 只有 `xxxxx` 一个正文块）：

```text
text    = "### 3\n\nxxxxx"
content = "# 1\n## 2\n\n### 3\n\nxxxxx"
```

规则：

- chunk 已经包含自身标题行时**不会重复**，只补祖先标题；
- 层级按原文保留（`# A` 下直接 `### C` 就输出 `# A` + `### C`，不臆造层级）；
- 空标题跳过；无标题且未发生分片包装的文档 `content == text`；
- `start / end / chars / 行号` 始终描述 `text`（原文切片），`--max-chars` 也只约束原文长度。

```bash
uv run chunk data/langchain-docs --preset langchain-docs --include-headings --verify
# 或
Chunker(ChunkConfig(include_headings=True))
```

## 分片包装

超长代码块 / 表格 / MDX 组件按行切开后，每个片段是独立的 chunk：它们不共享 chunk，
因此 `content` 可以安全地补齐上下文（`text` 不变，仍是精确切片）：

| 块类型 | 中间片段的 `content` |
| --- | --- |
| 代码 | 补上与原文一致的开围栏与闭围栏（如 ` ```python ` … ` ``` `） |
| 表格 | 重复表头行与对齐行（首行 + `---` 分隔行） |
| MDX | 首尾加组件名注释：`{/* <Tabs> */}` … `{/* </Tabs> */}` |

```text
text    = "print(42)"
content = "```python\nprint(42)\n```"
```

片段之间不会互相吞并，所以每个 `content` 都是自洽的 Markdown 片段；代价是长代码/长组件会产生
更多、更小的 chunk（可用 `min_chars` 合并普通小节，但不会合并同一块的两个片段）。

## 切分策略

1. **分块**：逐行扫描，识别标题（ATX 与 Setext）、代码围栏（``` / ~~~）、表格、引用、MDX 组件、列表、段落、分隔线、frontmatter、`export` 块。
2. **分节**：按标题层级构造标题栈，每个 chunk 归属唯一一节，并带上该节标题路径。
3. **打包**：同节内按块贪心累积到 `max_chars`，超出才断点；标题行始终与其正文首块同行。设置 `min_chars` 后，同一父节下、同一层级的相邻小节会先合并（不跨父节，且合并后仍不超 `max_chars`）；合并后的 chunk 采用第一个小节的标题路径，正文仍包含后续小节标题。
4. **超大块**：单个块超过上限时按行切分，优先落在子元素起始行（如 `<Tab>`、`<Step>`），其次空行，最后才选普通行；切出的片段在 `content` 中补围栏 / 表头 / 组件名（见上节）。
5. **丢弃**：`skip_kinds`（frontmatter / export / import / MDX 注释）与 `skip_prefixes`（LangChain 文档每页重复的索引横幅与页脚）不产出 chunk；它们会强制断开，避免混进相邻 chunk。`export` 块按大括号配平整段跳过（文档里的 `PatternEmbed` 组件有 45 KB）；`import` 无分号且没有 `{` / `(` 时只取一行，不会吞掉下一段正文。

**已知限制与设计取舍**：

- 标题行会与正文首块绑定；超长块按行切分并在 `content` 中补齐语义。只有三种情况会超过 `max_chars`：单行本身超长（无法在不破坏内容的前提下再切）；标题必须跟随正文首块（超出部分就是标题长度）；为避免尾部分隔符单独成块而并入上一片段（只多出分隔符的几个字符）。超长单行**正文**会按句末标点 → 逗号 → 硬切回退。
- `max_chars` 按**字符**而非 token 计量：中英文密度不同，需要 token 预算时请按语料换算后调整。
- 相邻 chunk **不重叠**：这是“偏移精确、可回溯”的刻意取舍；需要 overlap 的检索策略请在消费端处理。
- 不支持 4 空格缩进、**无围栏**的代码块（它更像列表续行或组件内容）；列表项内**带围栏**的代码（任意缩进）已支持。
- 列表项内的围栏代码会与列表分成相邻块（内容不丢失，通常仍落在同一个 chunk）；若需要片段自带的围栏/表头，请使用 `content`（`text` 始终不含合成内容）。
- `split_directory` 是单线程同步 IO；5 MB 语料约 0.5 s，更大规模建议按目录分片。
- 偏移按 Unicode 码点，且 `split_file` 用 `newline=""` 读取，保留原始 `\r\n`；浏览器/JS 定位需按 UTF-16 换算（`demo/static/app.js` 有示例）。
- 解析器是面向 Docusaurus / Nextra 的**启发式**实现，不是 CommonMark/MDX 规范解析器；复杂嵌套、字符串内大括号等边界可能与规范解析器不同。

## Python API

```python
from pathlib import Path

from langchain_md_chunker import Chunker, ChunkConfig

chunker = Chunker(ChunkConfig(max_chars=1200, include_headings=True))

chunks = chunker.split_directory("data/langchain-docs")   # 或 split_file / split_text
source = Path("data/langchain-docs", chunks[0].doc).read_text(encoding="utf-8")

assert source[chunks[0].start : chunks[0].end] == chunks[0].text
print(chunks[0].context, len(chunks))
```

其他常用选项：

```python
# 合并同一父节下的小节（不跨父节）
Chunker(ChunkConfig(min_chars=200))

# 内容寻址 id（相同内容跨文件共享 id）
Chunker(ChunkConfig(id_strategy="content"))

# 流式处理大语料；跳过无法解码的文件
for chunk in Chunker().iter_directory("data/langchain-docs", encoding="utf-8", on_error="skip"):
    index.add(chunk)
```

持久化与读取：

```python
from langchain_md_chunker import build_manifest, read_chunks, read_manifest, write_chunks

manifest = build_manifest(chunks, source_root="data/langchain-docs", config=chunker.config)
write_chunks(chunks, "data/chunks", manifest=manifest)

chunks = read_chunks("data/chunks")          # 目录或 .jsonl 均可
manifest = read_manifest("data/chunks")
```

与 LangChain 集成（可选，自行安装 `langchain-core`）：

```python
from langchain_md_chunker import to_langchain_documents

documents = to_langchain_documents(chunks)          # page_content 默认取 content
documents = to_langchain_documents(chunks, page_content="text")   # 精确原文
```

公开 API 即 `langchain_md_chunker.__all__`：`Chunker`、`ChunkConfig`、`Chunk`、`langchain_docs`、
`to_langchain_documents`、`verify_chunks`、`write_chunks`、`read_chunks`、`build_manifest`、`read_manifest` 及文件常量。
解析层（`blocks.py`）与切分层（`splitter.py`）属于内部实现，不作为兼容性承诺；
完整的公开接口清单见 [docs/api/index.md](https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/blob/main/docs/api/index.md)。

## 演示前端

```bash
uv run python demo/server.py --port 8000
```

- 左侧按源文件顺序列出 `[序号] 预览`，支持按路径 / 标题 / 预览片段过滤；预览取自 `content`，开启 `--include-headings` 后可直接看到标题前缀；
- 点击任意 `[序号]`，右侧直接渲染源文件并高亮该 chunk，自动滚动到高亮位置；
- 顶部显示文档路径、字符偏移、行号、标题路径，可另开原始文件；
- URL 形如 `http://127.0.0.1:8000/#c32352242f276a1b`，可直接分享某个 chunk。

前端没有构建步骤（原生 ES modules + HTML/CSS），服务端只用标准库，不导入 chunker 包，因此不会污染核心。修改语料后重新 `uv run chunk data/langchain-docs`，服务会自动重载。

## 目录结构

```
src/langchain_md_chunker/
├── __init__.py     # 公开 API（__all__）
├── blocks.py       # 内部：行 → Block（围栏/表格/MDX/引用…）
├── splitter.py     # 内部：Block → 分节打包 → RawChunk(偏移)
├── chunker.py      # 编排：文件 / 目录 + 标题前缀 → Chunk
├── models.py       # 输出模型 Chunk
├── config.py       # ChunkConfig（与语料无关的默认值）
├── presets.py      # 语料预设（langchain-docs）
├── storage.py      # JSONL + manifest 读写
├── verify.py       # 偏移一致性校验
└── cli.py          # `uv run chunk <INPUT>`
demo/
├── server.py       # 演示服务（stdlib）
└── static/         # index.html / app.js / styles.css
tests/
├── conftest.py         # 语料 fixture（全量切分只跑一次）
├── test_parser.py      # 围栏/表格/MDX/引用等解析边界
├── test_splitter.py    # 打包、标题上下文、超长块、样板剔除
├── test_chunker.py     # 文件/目录 API、编码（Unicode、CRLF）、校验、幂等
├── test_storage.py     # JSONL / manifest 往返
├── test_cli.py         # 命令行端到端与退出码
├── test_package.py     # 包入口、公开 API 与语料预设
├── test_fuzz.py        # 固定种子的随机文档不变量测试
├── test_docs.py        # 公开 API 文档覆盖与链接检查
└── test_demo.py        # 演示服务的数据装载、重载容错与路径安全
docs/api/               # API 参考（纯 Markdown，无需构建）
CHANGELOG.md            # 版本变更记录
RELEASING.md            # PyPI 发布流程与检查清单
data/download_docs.py
```

## 测试

```bash
uv run pytest                       # 229 项，秒级
uv run pytest --cov                 # 覆盖率（已配置分支覆盖）
uv run ruff check src demo tests    # 静态检查（ruff 已固定为 dev 依赖）
```

当前覆盖率：含语料时核心包 100% 行 / 100% 分支（`uv run pytest --cov` 可复现）；CI 无语料时门禁为 ≥99%。

测试关注的是**不变量**而不是实现细节：

- chunk 切片等于源文件 `[start, end)`，且行号、标题路径、上下文自洽；
- 代码围栏、表格、MDX 组件不会被“半个标签”切断，围栏内的 `#` 不当标题；
- Unicode（非 BMP 字符）、CRLF 文件的偏移按**原始文件**（保留 `\r\n`）的码点计；
- 文件/目录 API 的 `doc` 路径、排序稳定性与 `verify_chunks` 的负例；
- CLI 退出码、`--verify` 失败、`--max-chars`/`-p` 生效；
- 语料存在时对全量 4700+ chunk 校验：不重叠、不越界、ID 唯一、超长块占比 < 1%。

## 发布

PyPI 包名 `langchain-md-chunker`。版本号、构建、Trusted Publishing 配置与回滚流程见
[RELEASING.md](https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/blob/main/RELEASING.md)，
变更记录见 [CHANGELOG.md](https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/blob/main/CHANGELOG.md)。

```bash
uv build                      # 产物：dist/*.whl、dist/*.tar.gz
uvx --from twine twine check dist/*
```

## 版权

代码以 [MIT License](https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/blob/main/LICENSE) 发布。

`data/langchain-docs/` 中的文档版权归 LangChain 所有，仅用于本地学习与测试。
