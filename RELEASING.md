# 发布到 PyPI

包名：`langchain-md-chunker`（PyPI 上当前未被占用，发布前可再确认一次）。
默认发布方式：GitHub Actions + PyPI Trusted Publishing（无需长期 token）。

## 一次性准备

1. **许可证（必做，尚未完成）**：仓库目前没有 `LICENSE` 文件，`pyproject.toml` 也没有 `license` 字段。
   选定许可证后：
   - 添加 `LICENSE` 文件；
   - 在 `pyproject.toml` 的 `[project]` 中加入 SPDX 表达式，例如 `license = "MIT"`；
   - 重新构建并确认 `METADATA` 中出现 `License-Expression`。
2. **PyPI 账号**：注册 <https://pypi.org>，开启两步验证（发布必需）。
3. **Trusted Publisher**：在 PyPI 项目页面（首次发布前在 *Publishing* 设置里）添加
   GitHub publisher：
   - Owner：`Ashitaka-Laputa-IV`
   - Repository：`langchain-md-chunker`
   - Workflow：`publish.yml`
   - Environment：`pypi`
4. **GitHub Environment**：仓库 Settings → Environments 新建 `pypi`（可加人工审批）。

## 每次发布

```bash
# 1. 改版本号（两处必须一致，测试会检查）
#    pyproject.toml: version
#    src/langchain_md_chunker/__init__.py: __version__
#    并在 CHANGELOG.md 记录

# 2. 本地检查
uv run pytest
uv run ruff check src demo tests
uv run chunk data/langchain-docs --verify

# 3. 构建并检查元数据
rm -rf dist
uv build
uvx --from twine twine check dist/*

# 4. 安装产物做冒烟测试（别只测 editable 安装）
uv venv /tmp/pkg-smoke --python 3.13
uv pip install --python /tmp/pkg-smoke/bin/python dist/*.whl
/tmp/pkg-smoke/bin/chunk --help
/tmp/pkg-smoke/bin/python - <<'PY'
import importlib.metadata as md
from langchain_md_chunker import Chunker

meta = md.metadata("langchain-md-chunker")
print(meta["Name"], meta["Version"], meta["Requires-Python"])
chunk = Chunker().split_text("# T\n\nbody\n")[0]
print(chunk.text, chunk.start, chunk.end, chunk.content)
PY

# 5. 提交并打 tag，推送后由 CI 发布
git add -A
git commit -m "chore(release): v0.1.0"
git tag v0.1.0
git push origin main --tags
```

推送 tag 后 `.github/workflows/publish.yml` 会构建、`twine check`、再用 OIDC 上传到 PyPI。

### 手动发布（备用）

```bash
uv build
uv publish --token "$UV_PUBLISH_TOKEN"
```

## 发布前检查清单

- [ ] `pyproject.toml` 与 `__init__.__version__` 版本一致（`tests/test_release.py` 会拦截）
- [ ] `CHANGELOG.md` 已记录本次变更
- [ ] `README.md` 不含相对链接（PyPI 上会 404，测试会拦截）
- [ ] `LICENSE` 与 `license` 字段已配置
- [ ] 全量测试与 `ruff` 通过
- [ ] wheel 冒烟测试通过（CLI、导入、切分）
- [ ] sdist 体积正常（只含 `pyproject.toml`、`README.md`、`src/`）
- [ ] git tag 与版本号一致（`v0.1.0`）

## 回滚

PyPI 不允许删除已发布版本，只能 *Yank*：项目页面 → Manage → Releases → Yank。
Yank 后该版本仍可被精确版本安装，但不会出现在默认解析结果里。之后发布新的补丁版本修复。
