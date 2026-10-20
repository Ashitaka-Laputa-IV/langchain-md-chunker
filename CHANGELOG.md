# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.4.0] - 2026-10-20

### 新增

- **分片语义包装**：超长代码块 / 表格 / MDX 组件被切开后，`Chunk.content` 自动补回围栏、重复表头、标注组件名（`{/* <Tabs> */}`）；`text` 仍是精确原文切片。
- **内容寻址 id**：`ChunkConfig(id_strategy="content")` 用 `content` 的哈希生成 id，相同内容跨文件共享 id；两种策略都加宽为 `c` + 16 位十六进制。
- **小节合并**：`min_chars` 合并同一父节、同一层级的相邻小节（不跨父节），`merge_small_sections=False` 可关闭。
- **目录读取选项**：`split_directory` / `split_file` 新增 `encoding`；目录接口新增 `on_error="skip"`；新增流式迭代器 `Chunker.iter_directory`。
- `to_langchain_documents` 的 metadata 增加 `kind` / `lang`。

### 变更

- 超长块切出的每个片段现在是独立 chunk（不再与相邻片段/正文合并），确保补出的围栏、表头与组件注释始终闭合。
- chunk id 长度从 11 位十六进制加宽到 16 位；`location` 策略生成的 id 与 0.3.0 不兼容。
- CLI 新增 `--min-chars`、`--no-merge-small-sections`、`--id-strategy`、`--encoding`、`--on-error`。

### 文档

- 修正“原子块不可拆”的措辞：超长块按行切分，只有单行超长或为了避免尾部分隔符单独成块时才略微超过 `max_chars`。

## [0.3.0] - 2026-10-20

### 修复

- **标题被 `skip_prefixes` / `skip_kinds` 过滤时，整节正文会被静默删除**：标题范围现在取自标题块本身，而不是过滤后的首块。
- MDX 的 `import` 语句与 `{/* ... */}` 注释不再被当成正文（默认跳过 `import` / `comment` 块）。
- `***` 分隔线不再被吸入上一段落。

### 变更

- 超长单行**正文**按句末标点 → 逗号 → 硬切回退切分；代码/表格/组件按行切分（当时片段不带围栏/表头包装）。
- `Chunk` 新增 `kind`（`para`/`code`/`table`/`list`/`quote`/`mdx`/`mixed`）与 `lang` 字段。
- CLI 默认 `--preset generic`（不再默认套用某家文档站规则）；`INPUT` 支持单个文件。
- `split_directory` 跳过 `.git`、`.venv`、`node_modules` 等目录，默认模式覆盖 `*.MD` / `*.MDX`。

## [0.2.0] - 2026-10-20

### 变更

- 最低 Python 版本从 3.13 降至 **3.11**，并补充 3.11 / 3.12 classifier。
- 解析器支持 **Setext 标题**（`===` / `---` 下划线形式）。

### 新增

- `to_langchain_documents()`：可选适配 `langchain-core` 的 `Document`，惰性导入，不增加运行时依赖。

### 文档

- README 补充已知限制：字符（非 token）长度、无 overlap、缩进代码、列表内围栏、单线程 IO、码点偏移。
- 新增 `docs/api/integrations.md`。

## [0.1.0] - 2026-10-20

首个版本。

### 新增

- `Chunker`：`split_text` / `split_file` / `split_directory`，按标题分节并把每个 chunk 的
  源文件字符偏移写入元数据。
- `Chunk`：`text` 始终是原文精确切片，`content` 可按需带标题路径。
- `ChunkConfig`：`max_chars`、`skip_kinds`、`skip_prefixes`、`include_headings`。
- `presets.langchain_docs`：LangChain 文档的样板剔除预设（CLI 默认启用）。
- JSONL + manifest 存储（原子写）、`verify_chunks` 偏移校验。
- 命令行 `chunk` / `langchain-md-chunker`，支持 `--preset`、`--include-headings`、`--verify`。
- `demo/`：零构建的 chunk 浏览与源码高亮演示。
- `docs/api/`：公开 API 参考。

### 已知限制

- 单个不可拆的原子块（超长单行代码、大型 MDX 组件）可能超过 `max_chars`。
- `chunks.jsonl` 与 `manifest.json` 分别原子替换，不是跨文件事务。
- 仅支持 Python 3.13+。

[Unreleased]: https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Ashitaka-Laputa-IV/langchain-md-chunker/releases/tag/v0.1.0
