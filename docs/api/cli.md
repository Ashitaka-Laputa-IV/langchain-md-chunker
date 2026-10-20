# cli —— 命令行

console script：`chunk`（等价入口 `langchain-md-chunker`），实现为 `langchain_md_chunker.cli:main`。
输出全部为英文。

## 用法

```bash
uv run chunk <INPUT> [-o OUTPUT] [--max-chars 1500] [--preset langchain-docs|generic]
             [--include-headings] [-p PATTERN] [--verify] [--quiet]
```

## 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `INPUT` | **必填** | 源文档目录。不内置任何默认语料；目录不存在时退出码 `2`。 |
| `-o, --output` | `data/chunks` | chunk 输出目录 |
| `--max-chars` | `1500` | 单 chunk 软上限（原文字符数） |
| `--preset` | `langchain-docs` | `langchain-docs` 丢弃每页样板；`generic` 不丢弃。见 [presets.md](presets.md) |
| `--include-headings` | 关闭 | 把标题路径写入 `content`，见 [config.md](config.md) |
| `-p, --pattern` | `*.md`、`*.mdx` | 文件匹配模式，可重复 |
| `--verify` | 关闭 | 写盘前回读源文件校验偏移，见 [verify.md](verify.md) |
| `--quiet` | 关闭 | 只输出错误与警告 |

## 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 成功（包括“没有匹配文件”并写出空索引，此时 stderr 有 warning） |
| `1` | 读取源文件失败、校验失败、写入失败 |
| `2` | 参数错误：缺少 `INPUT`、目录不存在、非法 `--max-chars` |

## 输出

```text
$ uv run chunk data/langchain-docs --verify
180 documents -> 4461 chunks (avg 955.8 chars, max 6525), 0.54s
chunks  : data/chunks/chunks.jsonl
manifest: data/chunks/manifest.json
```

错误示例：

```text
$ uv run chunk /tmp/missing
error: source directory not found: /tmp/missing

$ uv run chunk data/langchain-docs --max-chars 0
error: max_chars must be positive

$ uv run chunk data/langchain-docs -p '*.rst'
warning: no files matched *.rst under data/langchain-docs; writing an empty index
```

## 常用组合

```bash
# 换语料：不做任何样板丢弃
uv run chunk path/to/docs --preset generic -o data/chunks

# 带标题前缀 + 校验
uv run chunk data/langchain-docs --include-headings --verify

# 只处理 mdx，且不打印进度
uv run chunk data/langchain-docs -p '*.mdx' --quiet
```

## Python 接口

| 名称 | 说明 |
| --- | --- |
| `main` | `main(argv: list[str] \| None = None) -> int`：解析参数并执行，返回退出码。不调用 `sys.exit`，console script 会把返回值作为退出码。 |
| `build_parser` | `build_parser() -> argparse.ArgumentParser`：返回配置好的参数解析器，便于测试或复用到其他脚本。 |

```python
from langchain_md_chunker.cli import main

code = main(["data/langchain-docs", "--verify", "-o", "data/chunks"])
```

```python
from langchain_md_chunker.cli import build_parser

args = build_parser().parse_args(["data/langchain-docs", "--include-headings"])
```
