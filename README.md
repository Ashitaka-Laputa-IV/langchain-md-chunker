# langchain-md-chunker

把 markdown / MDX 文档切成 chunk，并为每个 chunk 记录**源文件路径 + 字符偏移**，方便回溯原文。

核心是可复用的 Python 包（纯标准库、零运行时依赖）；`demo/` 里的网页只是演示，不参与打包。

## 特点

- **偏移精确**：chunk 是原文的精确切片，`source[start:end] == chunk.text` 恒成立（切分只挑断点，不改写、不拼接、不重复内容）。
- **MDX 感知**：跳过 frontmatter 与 `export const ...` 代码块；把 `<Tabs>`、`<CodeGroup>`、`<Accordion>` 等组件当作整体；代码围栏不会被腰斩。
- **标题感知**：按标题层级分节，chunk 携带该节的标题路径（如 `LangChain > Agents > Middleware`）作为上下文。
- **可调参数**：目标长度、合并阈值、要丢弃的块类型/样板前缀均可配置。

## 快速开始

```bash
uv sync                                        # 安装（含 dev 依赖）
uv run python data/download_docs.py            # 下载语料，约 180 篇 / 5 MB
uv run chunk --verify                          # 切分并校验偏移
uv run python demo/server.py                   # 打开 http://127.0.0.1:8000 浏览
```

## 切分命令

```bash
uv run chunk [INPUT] [-o OUTPUT] [--max-chars 1500] [--min-chars 250] [-p '*.md'] [--verify]
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `INPUT` | `data/langchain-docs` | 源文档目录 |
| `-o, --output` | `data/chunks` | chunk 输出目录 |
| `--max-chars` | `1500` | 单 chunk 目标上限（字符） |
| `--min-chars` | `250` | 过小 chunk 的合并阈值 |
| `-p, --pattern` | `*.md`, `*.mdx` | 文件匹配模式，可重复 |
| `--verify` | 关闭 | 写盘前回读源文件，逐条校验偏移 |

输出：

```
data/chunks/
├── chunks.jsonl    # 每行一个 chunk，保持源文件顺序
└── manifest.json   # 源目录、配置、统计信息
```

`data/langchain-docs/` 与 `data/chunks/` 都在 `.gitignore` 中：语料和派生产物可随时重建，不入库。

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
  "text": "## Context engineering\n\n..."
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

> 偏移以码点计（Python `str` 下标）。JavaScript 字符串是 UTF-16，跨码点时需
> `Array.from(text)` 后再切片——`demo/static/app.js` 已这样做。

## 切分策略

1. **分块**：逐行扫描，识别标题、代码围栏（``` / ~~~）、表格、引用、MDX 组件、列表、段落、分隔线、frontmatter、`export` 块。
2. **分节**：按标题层级构造标题栈，每个 chunk 归属唯一一节，并带上该节标题路径。
3. **打包**：同节内按块贪心累积到 `max_chars`；小于 `min_chars` 的 chunk 会并入相邻 chunk（前提是合并后仍不超限）。
4. **超大块**：单个块超过上限时按行切分，优先在空行处断开；代码块可能因此被切开，但偏移依然精确。
5. **丢弃**：`skip_kinds`（frontmatter / export）与 `skip_prefixes`（LangChain 文档每页重复的索引横幅与页脚）不产出 chunk；它们会强制断开，避免混进相邻 chunk。

**已知限制**：标题行会与正文首块绑定；若正文是单个不可拆的巨型块（超长单行代码、大组件），该 chunk 可能超过 `max_chars`。默认语料中此类情况约占 0.1%。

## Python API

```python
from pathlib import Path

from langchain_md_chunker import Chunker, ChunkConfig

chunker = Chunker(ChunkConfig(max_chars=1200, min_chars=200))

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

- 左侧按源文件顺序列出 `[序号] 预览`，支持按路径 / 标题 / 正文过滤；
- 点击任意 `[序号]`，右侧直接渲染源文件并高亮该 chunk，自动滚动到高亮位置；
- 顶部显示文档路径、字符偏移、行号、标题路径，可另开原始文件；
- URL 形如 `http://127.0.0.1:8000/#c32352242f27`，可直接分享某个 chunk。

前端没有构建步骤（原生 ES modules + HTML/CSS），服务端只用标准库，不导入 chunker 包，因此不会污染核心。修改语料后重新 `uv run chunk`，服务会自动重载。

## 目录结构

```
src/langchain_md_chunker/
├── __init__.py     # 公开 API
├── models.py       # Chunk / ChunkConfig
├── splitter.py     # 块解析 + 切分算法
├── chunker.py      # 文件 / 目录级封装
├── storage.py      # JSONL + manifest 读写
└── cli.py          # `uv run chunk`
demo/
├── server.py       # 演示服务（stdlib）
└── static/         # index.html / app.js / styles.css
tests/test_splitter.py
data/download_docs.py
```

## 测试

```bash
uv run pytest
```

测试覆盖：偏移精确性、标题路径、代码围栏、超长块切分、样板剔除、幂等边界；语料存在时还会校验全量 chunk 不重叠、不越界、长度分布合理。

## 版权

`data/langchain-docs/` 中的文档版权归 LangChain 所有，仅用于本地学习与测试。
