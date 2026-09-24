# 开发与构建

面向修改源码、运行测试与打包的说明。产品边界见 [设计](DESIGN.md)，分层职责见 [架构](ARCHITECTURE.md)。

## 环境

- Python 3.12.x（`pyproject.toml` 要求 `>=3.12,<3.13`，发布链固定在 3.12）
- Node.js 18+
- Microsoft Edge WebView2 Runtime
- `uv`：创建项目专用 `.venv` 并锁定依赖

```powershell
git submodule update --init --recursive
uv sync
cd node_renderer; npm ci; cd ..
cd tests/js; npm ci; cd ..
cd renderer; npm ci; npm run build; cd ..
```

## 运行

```powershell
python main.py                    # GUI（当前入口只启动界面，不解析命令行参数）
python tools/generate_demo.py     # 重新生成 samples/demo.html
```

## 测试

```powershell
python -m pytest -q               # 全部 Python 测试
cd tests/js; npm test; cd ..      # viewer 契约层（也可由 pytest 触发）
```

测试由四类组成：

- Python 单元与集成测试：转换计划、链接重写、图片内嵌、front matter、模板样式、打包脚本等。
- viewer / GUI / index 三套 JS 行为契约（jsdom + Node 内置 test runner）：在 `tests/js` 下驱动真实生成的页面，
  各自锁定契约条数与通过数，契约增减会显式失败而不是静默缩小覆盖。
- harness 自检：针对测试工具本身。
- 文档契约：`samples/demo.html` 必须等于当前源码重新生成的结果。

渲染相关测试需要本机 Node 与 `node_renderer/node_modules`；JS 层需要 `tests/js/node_modules`，缺少时相应层显式
skip 并说明原因，不会静默通过。自动化测试不覆盖 GUI 运行时交互、真实打印和打包后的 EXE；发布前按
[实机验收清单](QA-CHECKLIST.md) 执行验收。

## 目录

```text
core/                 转换计划、front matter、TOC、渲染调度、索引生成
gui/                  pywebview 界面与静态资源（gui/assets/）
node_renderer/        当前生产 renderer（markdown-it、footnote、texmath、KaTeX）
renderer/             新 renderer adapter（Phase 3，与 node_renderer 并存，尚未接入生产）
templates/default/    共享阅读器外壳
templates/Modern|Office|Vscode/   视觉主题（继承 default）
templates/index/      批量索引模板
templates/viewer.js   共享阅读器交互
templates/print.css   共享打印样式
packaging/            打包配置、图标、启动图与发布脚本
samples/              示例与渲染标本（demo.md 与入库的 demo.html）
tests/                自动化测试（tests/js 为 jsdom 层，不进打包）
tools/                辅助脚本（generate_demo.py、update_vscode_office.ps1；不参与打包）
upstream/             vscode-office 上游源码（submodule，只读；见 upstream/README.md）
```

## 上游 vscode-office

MarkdownReader 把 Markdown 语义交给 `vscode-office`：其源码以 **submodule** 放在 `upstream/vscode-office/`，
并 pin 在一个明确 commit 上（记录见 [upstream/pin.json](../upstream/pin.json)，说明见 [upstream/README.md](../upstream/README.md)）。

```powershell
pwsh tools/update_vscode_office.ps1 -Check                  # 只读检查：pin 一致性、上游是否被改动、结构证据
pwsh tools/update_vscode_office.ps1 -Update <ref>           # 显式更新到某个 commit / tag / 分支
pwsh tools/update_vscode_office.ps1 -ExpectCommit <sha>     # 断言当前 checkout
```

规则：不修改上游源码、不打 patch、不跟随 upstream `main`、不在 `upstream/` 内执行 `npm install`。
更新上游是显式操作：更新后同步 `upstream/pin.json` 并重新跑完整测试。
`tests/test_upstream_pin.py` 校验 `.gitmodules`、pin commit、上游工作区是否干净，以及 pin 记录里的证据路径与依赖版本是否仍然成立。

## 新 renderer（renderer/，Phase 3）

`renderer/` 是 MarkdownReader-owned 的新 adapter：复用 pinned vscode-office 的 Markdown 实现，
与生产路径 `node_renderer/` **并存**，尚未接入 GUI 或转换流程。

```powershell
cd renderer
npm ci          # 只安装 renderer 自己的依赖；绝不在 upstream 内安装任何东西
npm run build   # esbuild 打包到 renderer/dist/renderer.cjs（不入库，可重复构建）
npm test        # node:test 冒烟
cd ..
uv run pytest -q
```

- 构建输入：`renderer/entry.js` + 静态引用的 pinned 上游扩展 + `renderer/node_modules`。
- 构建前校验 upstream provenance：pin manifest == authoritative gitlink == checkout HEAD；
  三者不一致时**拒绝构建**（不写 dist、不谎报来源）；只读检查用 `node build/build.js --check-provenance`。
  同时要求 upstream worktree 干净（`git -C upstream/vscode-office status --porcelain` 为空，含 untracked）；
  检查只验证不修复，不会 restore / reset / checkout 或删除文件。
- sibling module resolution 由 `renderer/build/build.js` 的 `nodePaths` 指向 renderer/node_modules 解决；
  不使用全局 `NODE_PATH`、junction，也不修改或复制上游文件。
- `renderer/dist/` 不入库：先构建再跑 pytest；产物缺失时测试会**失败并给出构建提示**（不 skip、不假绿）。
- 协议：`{ "protocol_version": 1, "ok": true, "html", "headings", "features", "warnings" }`；
  失败同样是单个 JSON envelope + 退出码 1，诊断只走 stderr。

## 命名与路径约定

- 项目名、窗口标题与产物统一 `MarkdownReader`；npm 包标识为小写 `markdownreader-node-renderer`。
- 模板目录按实际路径写 `templates/Modern|Office|Vscode/`，配置中的模板 ID 是 `modern|office|vscode`。
- 浏览器存储键统一 `markdownreader-*`；配置文件为 `config.json`（仓库只保留 `config.example.json`）。
- WebView2 数据目录为 `%LOCALAPPDATA%\MarkdownReader\WebView2`。

## 构建与发布

```powershell
uv lock --check
uv sync --locked --extra build
python -m PyInstaller --clean --noconfirm --workpath "packaging\.pyinstaller-build" --distpath "dist" packaging\MarkdownReader.spec
```

- 内置 Node 运行时放在 `packaging/node/node.exe`（不进版本库；缺失时构建直接失败）。
- 校验产物：`python packaging/validate_release.py --mode both --wait 20`。
- 发布冻结：`python packaging/release_freeze.py --check-only` 校验版本与验收证据，`--tag` 在证据齐全后重建产物并打 tag。

细节见 [打包说明](../packaging/README.md)。


