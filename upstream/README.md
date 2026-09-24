# vscode-office 上游（只读）

本目录保存 `vscode-office` 的源代码 checkout，作为 MarkdownReader 的 Markdown 语义上游。

**这是第三方代码，不在本仓库维护范围内。**

| 项目 | 值 |
| --- | --- |
| 仓库 | https://github.com/cweijan/vscode-office.git |
| 许可证 | MIT |
| pin 的 commit | `908258dafc827ce0475fe7671d414914fbd3867b` |
| commit 日期 | 2026-08-16T08:01:41Z（Merge branch 'dev'） |
| 上游版本 | package.json version 4.2.0 |
| pin 记录 | [pin.json](pin.json)（机器可读，唯一事实源） |
| 接入阶段 | Phase 2，见 [重构路线图](../docs/REFACTOR_ROADMAP.md) |
| 兼容矩阵 | [迁移兼容矩阵](../docs/MARKDOWN_COMPATIBILITY.md) |

## 规则

1. 不修改 `upstream/vscode-office/` 内的任何文件。
2. 不把上游文件复制出来形成私有 fork。
3. 兼容处理一律放在 MarkdownReader 的 adapter 层（Phase 3 起）。
4. 不跟随 upstream `main`：更新必须显式给出 ref，并重新跑测试。
5. 不在 `upstream/` 内执行 `npm install` 或构建：保持工作区 pristine（无 node_modules、无构建产物）。
6. 上游工作区必须保持 clean；检查脚本会在脏时拒绝继续。

## 新 checkout 如何恢复完全相同的上游状态

```powershell
git clone <MarkdownReader 仓库地址> MarkdownReader
cd MarkdownReader
git submodule update --init --recursive
uv sync
cd node_renderer; npm ci; cd ..
cd tests/js; npm ci; cd ..
pwsh tools/update_vscode_office.ps1 -Check
```

`git submodule update --init --recursive` 按 `.gitmodules` 里的绝对 URL 拉取上游，并把工作区切到父仓库记录的 gitlink commit，与 `pin.json` 的 `pinned_commit` 相同。
不要手工复制上游目录：pin 记录与检查脚本都会校验这一点。

## 更新上游（显式操作）

```powershell
pwsh tools/update_vscode_office.ps1 -Check                        # 只读检查（默认）
pwsh tools/update_vscode_office.ps1 -Update <sha 或 tag 或分支>    # 显式更新
pwsh tools/update_vscode_office.ps1 -ExpectCommit <sha>           # 断言当前 checkout
```

更新之后必须人工完成：更新 `upstream/pin.json`、跑完整测试（`uv run pytest -q`、`uv run pytest -q --runxfail tests/test_markdown_compat_target.py`、`uv run ruff check .`）、检查 `git diff --submodule=diff` 并提交新的 gitlink。
脚本不会自动提交、不会 push、不会切换用户分支、不会跟随 upstream main。

## Markdown 相关入口（Phase 3 地图）

```text
src/service/markdownService.ts          导出入口：pdf / html / docx
src/service/markdown/markdown-pdf.js    markdown-it 装配：插件注册、图片路径、样式注入
src/service/markdown/html-export.js     HTML / DOCX 输出
src/service/markdown/outline.js         目录与大纲
src/service/markdown/wikilink/          WikiLink 解析与文件检索
src/service/markdown/ext/               自定义扩展：katex / mermaid / obsidian / front-matter
src/service/markdown/yamlProperties.js  front matter 属性面板（AGENTS 6 不启用）
template/template/template.html         导出 HTML 外壳
template/styles/                        arduino-light.css / markdown.css / markdown-pdf.css
test/markdown/                          Markdown 标本库（Callouts.md 等），不是单元测试
```

## 已知差异（留给 Phase 3/4，本阶段不修改）

- footnote：上游该 commit 没有实现，继续由 MarkdownReader 拥有。
- 图片：上游 HTML 导出把 src 重写为 `file://` URL，不是 data URI；standalone 内嵌仍由 MarkdownReader 负责。
- TOC：上游只在 pdf 导出自动注入 `[toc]`，html 导出需要正文写 `[toc]`。
- 代码高亮：上游服务端使用 highlight.js，MarkdownReader 目前不预高亮。
- front matter：上游会渲染属性面板，AGENTS 6 明确不启用该行为。

## 如何撤销这个 submodule

```powershell
git submodule deinit -f upstream/vscode-office
git rm --cached upstream/vscode-office
# 然后手动删除 .gitmodules 中的条目与 upstream/vscode-office 目录
```
