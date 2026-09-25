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
core/viewer_assets.py 阅读器/主题资产的唯一来源（外壳、脚本、样式链、注册表）
gui/                  pywebview 界面与静态资源（gui/assets/）
renderer/             生产 renderer（v2 adapter，产物 renderer/dist 随包发布）
node_renderer/        v1 回退 renderer（markdown-it、footnote、texmath、KaTeX）
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
npm run build   # esbuild 打包到 renderer/dist/renderer.cjs，并发布 dist/katex/ 与 dist/mermaid/（均不入库）
npm test        # node:test（协议冒烟 + 资源与资产逻辑单测）
cd ..
uv run pytest -q
pwsh tools/run_browser_acceptance.ps1   # opt-in：真实浏览器离线渲染 Mermaid（默认 pytest 不含）
```

- 构建输入：`renderer/entry.js` + 静态引用的 pinned 上游扩展 + `renderer/node_modules`。
- 构建前校验 upstream provenance：pin manifest == authoritative gitlink == checkout HEAD；
  三者不一致时**拒绝构建**（不写 dist、不谎报来源）；只读检查用 `node build/build.js --check-provenance`。
  同时要求 upstream worktree 干净（`git -C upstream/vscode-office status --porcelain` 为空，含 untracked）；
  检查只验证不修复，不会 restore / reset / checkout 或删除文件。
- sibling module resolution 由 `renderer/build/build.js` 的 `nodePaths` 指向 renderer/node_modules 解决；
  不使用全局 `NODE_PATH`、junction，也不修改或复制上游文件。
- `renderer/dist/` 不入库：先构建再跑 pytest；产物缺失时测试会**失败并给出构建提示**（不 skip、不假绿）。
- `renderer/dist/katex/` 是 companion runtime asset（Phase 5A）：构建把 `node_modules/katex/dist` 的样式与它引用的字体
  复制过去（只读、不联网），使 renderer 运行期不依赖 `renderer/node_modules`；因此 `dist/` 单独拷出去也能产出带公式的 HTML。
- `renderer/vendor/mermaid/<version>/` 是 vendored 的正式 browser 构建（产物 + MIT LICENSE + metadata.json，含 SHA-256）。
  `npm run build` 只**校验**并复制到 `dist/mermaid/`，不联网、不更新；升级只走
  `pwsh tools/update_mermaid_runtime.ps1 -Version <version>`（唯一联网入口，见 `renderer/vendor/mermaid/README.md`）。
- 资产发布是 **staged + verified + rollback-protected replacement**（Phase 5B）：`renderer.cjs` / `katex/` / `mermaid/`
  先写进 `dist/.staging/` 并复验（含 vendored runtime 的 SHA-256），staging 无论成败都会清理；安装前把旧资产移到
  `dist/.backup/`，全部成功即清理，**中途失败则回滚**到旧 managed set（rollback 自身失败时保留 `.backup/` 并明确报出路径）。
  因此：**构建/校验失败发生在安装之前**，正式 dist 完全不变；**安装中途失败**由 rollback contract 恢复旧 set。
  三个独立路径**不构成**文件系统级原子事务，这里也不这么声称。
- 浏览器验收（Phase 5B，opt-in）：`tests/browser` 用真实 adapter 渲染 → 自装配页面 → 拦截所有非 `file://` 请求
  → 断言 `.mermaid` 容器内真的生成 `<svg>`，并锁定 D2 不变式（DOM 文本 == 作者原文）；另有 mixed 用例证明
  「invalid 图在前、valid 图在后」时后者仍渲染成功且无未捕获错误。默认 pytest **不依赖浏览器**。
- 网络层（Phase 5C）：`renderer/resources/http_client.js` 负责传输（GET / timeout 8 s / retries 1 / retry delay 150 ms /
  单资源 16 MiB / 只接受 `image/*`，缺 Content-Type 才按扩展名回退），`renderer/resources/remote_resolver.js`
  负责 URL 级 cache（同一 URL 一个 Promise）与并发调度（上限 4，结果按文档顺序写回）。默认 `fetch_remote_resources=true`；
  失败一律保留作者原引用 + 可读 warning 并继续转换。
  数值 option（`resource_timeout_ms` / `resource_retries` / `resource_max_bytes`）只在有效范围内生效，越界
  （非正数 / retries 为负或非整数）一律回落默认值；retry 分类在 fetch 阶段与 **body 读取阶段共用同一套规则**
  （`AbortError` / `TimeoutError` → timeout，其它读错误 → network，两者都可 retry；只有超限 `too-large` 不 retry，
  且每次 retry 都是完整重新 GET）。
- 测试**不依赖公共互联网**（Phase 5C gate）：`tests/renderer_adapter.py::render()` 默认注入 `fetch_remote_resources=false`，
  因此 `uv run pytest` / `npm test` 不会联网；真实联网语义只在 `tests/test_renderer_network.py` 里用
  127.0.0.1 loopback 服务器（`tests/loopback_http.py`）验证。
- standalone closure（Phase 5D）：`core/html_assembly.py` 把 v2 envelope 装配成完整 HTML，注入顺序确定
  （`<head>` = viewer.css → theme 链 → `resources.styles` → print.css；`</body>` 前 = viewer.js → numbering →
  各 script 的 `script` 后 `boot`），并返回注入账本（label + position + bytes）；`tools/standalone_closure.py`
  判定 closure（四态与 severity 见 K24，证据按 occurrence 消费），缺 `--envelope` 时走 strict 模式。自检入口：
  `uv run python tools/standalone_closure.py samples/demo.html`（生产 v1 产物基线 → standalone）、
  `uv run python tools/assemble_document.py --out build/smoke.html`（装配集成页：本地图片 + KaTeX + Mermaid）、
  `pwsh tools/run_browser_acceptance.ps1 -ExtraPage build/smoke.html`（opt-in：真实浏览器离线打开该页）。
- author provenance（Cutover C1）：`renderer/document/author_references.js` 在 **token 层**记录作者 raw HTML 的外部
  subresource 引用，产出 `resources.author_references = [{ ref, count }]`（每 ref 一条、首次出现顺序、普通文档 `[]`）；
  只记录来源（不 fetch、不改 html、不进 `items`），因此 raw HTML 与 Markdown 生成的 html 始终可区分。
  规则与 closure checker 同构，两侧由 `tests/fixtures/author_references.json` 强制对齐（node 直测 scanner +
  spawn dist，pytest 走真实 dist）；`tools/standalone_closure.py` 缺省自动消费该通道，`--author-refs` 只在需要覆盖时使用。
- 协议：v2（Phase 5A）——
  `{ "protocol_version": 2, "ok": true, "html", "headings", "features", "warnings",`
  `"resources": { "items": [], "styles": [], "scripts": [], "author_references": [] } }`；
  `resources` 是**必在**字段（没有资源时也是空结构）：`items` 是资源 manifest，`styles` 是交给 assembler 注入的 CSS，
  `scripts` 是按需交付的运行时（今天只有 mermaid），`author_references` 是作者 raw HTML 的 provenance（Cutover C1，见 K25）；
  `warnings` 保持用户可读字符串数组，成功内嵌不产生 warning（状态记在 manifest）。
  失败同样是单个 JSON envelope + 退出码 1，诊断只走 stderr。v1 的 `assets.css` 只属于 v1（Cutover C4 后是回退路径）。
- renderer 选择（Cutover C2，K26）：`core.renderer_node.render_markdown_node(markdown, context=…,
  renderer_version="v1", options=None)` —— **显式**选择 v1 / v2；这是 bridge，默认 `v1`（它是低层 API，
  production policy 见下一条）。
  `core/renderer_v2.py` 负责调用 `renderer/dist/renderer.cjs`、校验 `protocol_version == 2` 与必在形状、
  原样返回**完整** envelope；Node 可执行文件解析与版本下限（v2 需 major >= 18，常量 `MINIMUM_NODE_MAJOR`
  也由 `packaging/MarkdownReader.spec` 在构建期断言）属于 `core/renderer_node.py`。
  不做协议探测、不在 v2 失败时回退 v1、artifact 缺失给出构建提示；`options` 只对 v2 生效
  （v1 收到非空 options 报 `ValueError`，不静默忽略）。
- converter 的 v2 路径（Cutover C3，K26）：`process_single` / `process_batch` 增加**内部** keyword
  `renderer_version`（默认 = `core.config.PRODUCTION_RENDERER_VERSION`）与 `renderer_options`。
  v2 时 renderer 走 C2 的 bridge，装配交给 `core/html_assembly.py`（含注入账本）；
  `report["warnings"]` 固定为 **renderer warnings + assembly warnings**（顺序即此顺序）。
  v2 的 production 内部默认是 `_V2_DEFAULT_OPTIONS = {"math": True, "fetch_remote_resources": True}`，
  `renderer_options` 在其上覆盖，**不进 config.json**（Phase 8 才决定哪些 renderer 选项成为产品配置）。
  失败语义与 v1 对齐：模板不可装配 → log + 返回 `None`（不写文件）；renderer / bridge 失败保留
  actionable 异常（缺 artifact 不被吞成静默无输出）；未知 `renderer_version` 明确报错，不静默按 v1 处理。
  `core/converter.py` 运行期**不调用** closure checker（它只是 test / release gate）。
- production renderer policy（Cutover C4，K26）：`core/config.py::PRODUCTION_RENDERER_VERSION`（现为 `"v2"`）
  是**唯一**的默认来源。它不经 `_DEFAULTS`、不进 `config.json`、GUI 不可覆盖 —— 这是源码级 policy，
  不是用户设置；**回退 = 把这一行改回 `"v1"` 并重建**（v1 的 renderer、装配与打包资产都保留）。
  GUI 启动校验跟随 policy：`validate_renderer_runtime_for(PRODUCTION_RENDERER_VERSION)`，因此
  「包内缺 `renderer/dist`」或「Node < 18」会在**启动时**失败，而不是转换到一半。
- 发布包与验收（Cutover C4）：`renderer/dist/`（`renderer.cjs` + `katex/` + `mermaid/`）是新的必需载荷，
  spec 的 `REQUIRED_FILES` 与 `packaging/validate_release.py::RUNTIME_FILES` 两处断言；`release_freeze.py`
  在 PyInstaller 之前自动 `npm ci` + `npm run build`（只构建一次，两种形态共用）。构建期用**将被打包的**
  `node.exe` 对 v1 与 v2 各冒烟一次。实机验收记录必须与当前 production renderer 对应
  （`docs/QA-CHECKLIST-1.0.0-rc1-v2.md`；v1 时代记录只作历史，`release_freeze` 只认 `--qa-record` 指定的那份）。

- 阅读器资产层（Phase 6A）：`core/viewer_assets.py` 是"阅读器由哪些文件组成"的唯一来源（页面外壳、viewer 脚本、
  打印样式、样式链、主题注册表）。`core/config.py` 只管 config.json 与 bundle 路径，且**不反向依赖**它；
  `core/converter.py`（v1 回退）与 `core/html_assembly.py`（v2）都只经它取资产，`gui/api.py` 的主题列表也来自它。
  契约清单与"哪些可以改"见 [Viewer 契约](VIEWER_CONTRACT.md)；Phase 6B 把资产搬到 `viewer/` 与
  `themes/builtin/<id>/` 时**只改这一个模块**。

## 命名与路径约定

- 项目名、窗口标题与产物统一 `MarkdownReader`；npm 包标识为小写 `markdownreader-node-renderer`。
- 模板目录按实际路径写 `templates/Modern|Office|Vscode/`，配置中的模板 ID 是 `modern|office|vscode`（Phase 6B 计划改为 `themes/builtin/<id>/`，届时目录名与 id 统一；契约见 [Viewer 契约](VIEWER_CONTRACT.md)）。
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


