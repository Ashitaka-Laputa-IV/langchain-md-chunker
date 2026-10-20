# langchain-md-chunker

把 markdown / MDX 文档切成 chunk，并为每个 chunk 记录**源文件路径 + 字符偏移**，方便回溯原文。

核心是可复用的 Python 包（纯标准库、零运行时依赖）；`demo/` 里的网页只是演示，不参与打包。

API 参考见 [docs/api/index.md](docs/api/index.md)。

## 特点

- **偏移精确**：chunk 是原文的精确切片，`source[start:end] == chunk.text` 恒成立（切分只挑断点，不改写、不拼接、不重复内容）。
- **MDX 感知**：跳过 frontmatter 与 `export const ...` 代码块；把 `<Tabs>`、`<CodeGroup>`、`<Accordion>` 等组件当作整体；代码围栏不会被腰斩。
- **标题感知**：按标题层级分节，chunk 携带该节的标题路径（如 `LangChain > Agents > Middleware`）作为上下文。
- **标题可写入正文**（可选）：`--include-headings` 会把标题路径按原层级拼进 `content`，更适合 embedding；`text` 仍保持精确切片。
- **可调参数**：目标长度、要丢弃的块类型/样板前缀均可配置。

## 快速开始

```bash
uv sync                                        # 安装（含 dev 依赖）
uv run python data/download_docs.py            # 下载语料，约 180 篇 / 5 MB
uv run chunk data/langchain-docs --verify      # 切分并校验偏移（目录需显式指定）
uv run python demo/server.py                   # 打开 http://127.0.0.1:8000 浏览
```

## 切分命令

```bash
uv run chunk <INPUT> [-o OUTPUT] [--max-chars 1500] [-p '*.md'] [--include-headings] [--verify] [--quiet]
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `INPUT` | 必填 | 源文档目录（不内置任何默认语料） |
| `-o, --output` | `data/chunks` | chunk 输出目录 |
| `--preset` | `langchain-docs` | 语料预设：`langchain-docs` 丢弃每页样板，`generic` 不丢弃 |
| `--max-chars` | `1500` | 单 chunk 目标上限（字符，针对原文） |
| `-p, --pattern` | `*.md`, `*.mdx` | 文件匹配模式，可重复 |
| `--include-headings` | 关闭 | 把标题路径写进 `content`（见下节） |
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

核心包本身不知道任何具体语料，默认配置**不做语料相关的丢弃**。CLI 默认启用 `langchain-docs` 预设（丢弃每页重复的索引横幅与页脚）；换成别的文档集时用 `--preset generic`，或在 Python 里显式选择：

```python
from langchain_md_chunker import Chunker, langchain_docs

chunker = Chunker(langchain_docs(max_chars=1200))   # 或 Chunker() 走通用默认
```

自有语料可以自己组合配置：`ChunkConfig(skip_kinds=(...), skip_prefixes=(...))`；预设只是返回 `ChunkConfig` 的工厂函数，见 `presets.py`。分层与扩展点见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 数据格式

`chunks.jsonl` 单行示例：

```json
{
  "id": "c32352242f27",
  "doc": "oss/python/concepts/context.md",
  "start": 181,
  "end": 1541,
  "start_line": 5,
  "end_line": 27,
  "chars": 1360,
  "headings": ["Context overview", "Context engineering"],
  "context": "Context overview > Context engineering",
  "text": "## Context engineering\n\n...",
  "content": "# Context overview\n\n## Context engineering\n\n..."
}
```

| 字段 | 说明 |
| --- | --- |
| `id` | 由 `doc + start + end` 派生的稳定 ID |
| `doc` | 相对 `manifest.source_root` 的源文件路径 |
| `start` / `end` | 半开区间 `[start, end)`，单位是 **Unicode 码点** |
| `start_line` / `end_line` | 1-based 行号，闭区间 |
| `chars` | `end - start` |
| `headings` | 标题路径（由外到内） |
| `context` | `headings` 用 ` > ` 拼接，可直接拼到 embedding 输入前 |
| `text` | 原文切片，逐字符等于 `source[start:end]` |
| `content` | 用于 embedding / 展示的文本：默认等于 `text`，开启 `include_headings` 后是“标题路径 + 空行 + text” |

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
- 空标题跳过；无标题的文档 `content == text`；
- `start / end / chars / 行号` 始终描述 `text`（原文切片），`--max-chars` 也只约束原文长度；
  实测语料上 `content` 平均比 `text` 多 43 字符（最大 137）。

```bash
uv run chunk data/langchain-docs --include-headings --verify   # 产物带标题前缀
# 或
Chunker(ChunkConfig(include_headings=True))
```

## 切分策略

1. **分块**：逐行扫描，识别标题、代码围栏（``` / ~~~）、表格、引用、MDX 组件、列表、段落、分隔线、frontmatter、`export` 块。
2. **分节**：按标题层级构造标题栈，每个 chunk 归属唯一一节，并带上该节标题路径。
3. **打包**：同节内按块贪心累积到 `max_chars`，超出才断点；标题行始终与其正文首块同行。
4. **超大块**：单个块超过上限时按行切分，优先落在子元素起始行（如 `<Tab>`、`<Step>`），其次空行，最后才选普通行；代码/组件可能因此被切开，但偏移依然精确。
5. **丢弃**：`skip_kinds`（frontmatter / export）与 `skip_prefixes`（LangChain 文档每页重复的索引横幅与页脚）不产出 chunk；它们会强制断开，避免混进相邻 chunk。`export` 块按大括号配平整段跳过（文档里的 `PatternEmbed` 组件有 45 KB），并以标题/围栏为安全边界，绝不会吞掉正文。

**已知限制**：标题行会与正文首块绑定；若正文是单个不可拆的巨型块（超长单行代码、大组件），该 chunk 可能超过 `max_chars`。默认语料中此类情况约占 0.1%。

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

持久化与读取：

```python
from langchain_md_chunker import build_manifest, read_chunks, read_manifest, write_chunks

manifest = build_manifest(chunks, source_root="data/langchain-docs", config=chunker.config)
write_chunks(chunks, "data/chunks", manifest=manifest)

chunks = read_chunks("data/chunks")          # 目录或 .jsonl 均可
manifest = read_manifest("data/chunks")
```

公开 API：`Chunker`、`ChunkConfig`、`Chunk`、`split_text`、`parse_blocks`、`verify_chunks`、`write_chunks`、`read_chunks`、`build_manifest`、`read_manifest`。

## 演示前端

```bash
uv run python demo/server.py --port 8000
```

- 左侧按源文件顺序列出 `[序号] 预览`，支持按路径 / 标题 / 预览片段过滤；预览取自 `content`，开启 `--include-headings` 后可直接看到标题前缀；
- 点击任意 `[序号]`，右侧直接渲染源文件并高亮该 chunk，自动滚动到高亮位置；
- 顶部显示文档路径、字符偏移、行号、标题路径，可另开原始文件；
- URL 形如 `http://127.0.0.1:8000/#c32352242f27`，可直接分享某个 chunk。

前端没有构建步骤（原生 ES modules + HTML/CSS），服务端只用标准库，不导入 chunker 包，因此不会污染核心。修改语料后重新 `uv run chunk data/langchain-docs`，服务会自动重载。

## 目录结构

```
src/langchain_md_chunker/
├── __init__.py     # 公开 API
├── blocks.py       # 解析层：行 → Block（围栏/表格/MDX/引用…）
├── splitter.py     # 切分层：Block → 分节打包 → RawChunk(偏移)
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
└── test_demo.py        # 演示服务的数据装载、重载容错与路径安全
docs/api/               # API 参考（纯 Markdown，无需构建）
data/download_docs.py
```

## 测试

```bash
uv run pytest                       # 134 项，秒级
uv run pytest --cov                 # 覆盖率（已配置分支覆盖）
uv run ruff check src demo tests    # 静态检查（ruff 已固定为 dev 依赖）
```

当前覆盖率：核心包 100% 行 / 100% 分支（`uv run pytest --cov` 可复现）。

测试关注的是**不变量**而不是实现细节：

- chunk 切片等于源文件 `[start, end)`，且行号、标题路径、上下文自洽；
- 代码围栏、表格、MDX 组件不会被“半个标签”切断，围栏内的 `#` 不当标题；
- Unicode（非 BMP 字符）、CRLF 文件的偏移按码点而非字节；
- 文件/目录 API 的 `doc` 路径、排序稳定性与 `verify_chunks` 的负例；
- CLI 退出码、`--verify` 失败、`--max-chars`/`-p` 生效；
- 语料存在时对全量 4400+ chunk 校验：不重叠、不越界、ID 唯一、超长块占比 < 1%。

## 版权

`data/langchain-docs/` 中的文档版权归 LangChain 所有，仅用于本地学习与测试。
