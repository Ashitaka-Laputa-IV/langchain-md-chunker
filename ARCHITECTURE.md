# 架构说明

本文说明 `langchain-md-chunker` 的分层、依赖方向与扩展点，以及为什么这样切分。

## 目标

1. **核心可复用**：切分逻辑与具体语料无关，可当库用、可不带 demo 用。
2. **偏移可回溯**：任何 chunk 都能用 `start/end` 精确回到源文件，切分不改写文本。
3. **演示不污染核心**：`demo/` 只是消费者，不参与打包，核心不导入 demo 代码。

## 分层

```
┌──────────────────────────────────────────────────────────────┐
│ 接口层     cli.py                demo/server.py + static     │
├──────────────────────────────────────────────────────────────┤
│ 编排层     chunker.py             （文件/目录遍历、装配 Chunk） │
│            verify.py              （偏移一致性校验）            │
├──────────────────────────────────────────────────────────────┤
│ 算法层     splitter.py            （标题分节、打包、超长拆分）    │
│            blocks.py              （行 → Block 解析）           │
├──────────────────────────────────────────────────────────────┤
│ 模型/配置  models.py  config.py  presets.py                   │
├──────────────────────────────────────────────────────────────┤
│ 持久化     storage.py             （JSONL + manifest，原子写）  │
└──────────────────────────────────────────────────────────────┘
```

依赖方向严格向下，没有反向或环形依赖：

```
cli ──► chunker ──► splitter ──► blocks
 │         │            │
 │         └──► models  └──► config
 ├──► storage ──► models/config
 ├──► verify  ──► models
 └──► presets ──► config
```

## 数据流

```
文件文本
  │  blocks.py: 逐行扫描，产出 Block(kind, start, end, level, title, lang)
  ▼
Block 序列
  │  splitter.py: 按标题栈分节 → 每节内贪心打包成 [start, end)
  ▼
RawChunk（偏移 + 标题路径 + 是否以自身标题开头）
  │  chunker.py: 绑定 doc/id，切片得到 text，按需合成 content
  ▼
Chunk（text 精确切片 / content 可带标题前缀）
  │  storage.py: 序列化 JSONL + manifest
  ▼
data/chunks/chunks.jsonl
```

`RawChunk` 与 `Chunk` 的分离是刻意的：

- `splitter` 只关心“切哪里”，不知道文档路径，便于单测和复用；
- `chunker` 负责“这份文档的第几段”、ID、以及给 embedding 用的 `content`。

## 关键设计决策

### 1. 只挑断点，不改写文本

所有输出都以字符偏移表达，`source[start:end] == chunk.text` 是不变量。标题前缀、样板丢弃都只影响
`content` 或“是否产出 chunk”，不改变 `text` 与偏移。这样：

- 前端可以精确高亮，`verify_chunks` 可以回读校验；
- 下游做增量更新时，偏移仍然稳定。

### 2. 解析与切分分离

`blocks.py` 只回答“这一行/这一段是什么块”，`splitter.py` 只回答“哪些块组成一个 chunk”。解析规则
（围栏长度、MDX 嵌套、export 大括号配平）与打包策略（`max_chars`、子元素断点）互不影响，测试也按层拆分。

### 3. 跳过块即硬断点

frontmatter、`export` JS 组件、语料样板并不产出 chunk，同时会把相邻 chunk 强制断开，避免它们作为“两个块
之间的空隙”混进正文。

### 4. 语料差异用预设表达

`ChunkConfig` 的默认值不含任何语料特征（`skip_prefixes=()`）。LangChain 文档每页重复的横幅/页脚放在
`presets.langchain_docs()` 里，由 CLI 默认选用。换语料时用 `--preset generic` 或自己拼 `ChunkConfig`，
不需要改核心代码。

### 5. 持久化是唯一有副作用的层

`storage.py` 负责文件布局与原子替换（临时文件 + `os.replace`），因此切分过程中刷新演示页面不会读到半份索引。
其余模块保持纯函数式：同样的输入必然得到同样的 chunk 列表。

## 扩展点

| 需求 | 改动位置 |
| --- | --- |
| 支持新的 Markdown/MDX 写法 | `blocks.py` 增加块识别，配 `tests/test_parser.py` |
| 改变打包策略 | `splitter.py` 的 `_emit_unit` / `_split_oversized` |
| 新的可见元数据（如代码语言） | `Block` 已有 `lang`，在 `Chunk` 加字段并更新 `to_dict/from_dict` |
| 新的语料样板 | `presets.py` 增加工厂函数，CLI 增加 preset 选项 |
| 新的输出格式（Parquet 等） | 新增 `storage_xxx.py`，复用 `Chunk.to_dict()` |
| 新的消费端 | 只读 `chunks.jsonl` + `manifest.json`，参考 `demo/server.py` |

## 边界与约束

- **demo 不导入核心包**：服务端只读磁盘产物；核心变更不会破坏演示，反之亦然。
- **核心无第三方依赖**：安装即可用，demo 也只用标准库。
- **`manifest.json` 记录配置**：`max_chars`、预设/跳过规则、`include_headings`，便于复现与排查。
- **已知非事务点**：`chunks.jsonl` 与 `manifest.json` 各自原子替换，但不是跨文件事务；极端情况下读者可能
  短暂看到“新 chunk + 旧 manifest”。这是为简化实现而接受的取舍。

## 测试策略

- `test_parser.py` / `test_splitter.py`：按层验证解析与打包的边界行为；
- `test_chunker.py`（含 `verify_chunks`）/ `test_storage.py` / `test_cli.py`：API、持久化、命令行、错误路径；
- `test_fuzz.py`：固定种子的随机文档，只校验结构性不变量（切片精确、有序不重叠、行边界、行号）；
- `conftest.py`：真实语料只加载一次，全量切分做不变量检查（不重叠、ID 唯一、超长块占比）。

核心包当前行/分支覆盖率 100%，语料产物在重构前后保持逐字节一致，可作为“纯结构改动”的验收标准。
