# MarkdownReader 更新日志

## [1.0.0-rc1] - 2026-09-22

### 发布工程

- Python 依赖改为 `pyproject.toml` 分层声明（runtime / build / test / lint），由 `uv.lock` 锁定解析；`requirements.txt` 退役。
- PyYAML 成为正式运行依赖，删除「有则用、无则退化」的双模式；同时修掉块标量结尾换行被丢弃的解析缺陷。
- Node 运行时归入应用生命周期：进程内只校验一次；frozen 包只使用内置 Node，缺失即视为打包物损坏；源码运行仍可使用系统 Node。
- spec 增加发布资源硬清单与构建模式白名单，并校验内置 Node 的版本与 SHA-256（`packaging/node-runtime.json`）。
- 新增 `packaging/validate_release.py`：对 onefile 与 onedir 产物做存在性、体积、资源与启动存活校验。
- 关闭 UPX；同一 spec 支持 `onefile`（默认）与 `onedir`（`MR_BUILD_MODE=onedir`）。
- `config.json` 退出版本库，改为 `config.example.json` 与 `.gitignore`。
- 启动日志同时写入 EXE 同级目录的 `MarkdownReader.log`。
- 测试增至 108 项：三层行为契约（viewer 21 / GUI 8 / index 9）、harness 自检 5 条，以及前后端单元与集成用例。
- 仓库文档（README、DESIGN、ARCHITECTURE、ROADMAP、release-readme）与上述实现对齐。

### 修复

- 关闭 markdown-it 的模糊链接识别（`fuzzyLink: false`）：正文里的裸文件名（`README.md`、`report.md`、`版本 1.2.3`）不再被当成互联网域名并生成 `http://xn--…` 假链接；带 scheme 的真 URL 与显式 Markdown 链接不受影响。
- KaTeX 资源改为按需内联：文档正文没有任何公式时不再注入 KaTeX 样式与字体。此前每篇 HTML 都无条件携带约 1.4 MB 的 base64 字体，几百字节的文档同样膨胀到约 1.5 MB；现在是否内联由渲染结果是否产出 KaTeX 标记决定，代码块里的 `$`、价格 `$100` 与转义 `\$` 都不会触发，含公式的文档行为完全不变。

### 版本

- 版本收敛为 1.0.0-rc1（`pyproject.toml` 记为 `1.0.0rc1`）；1.0.0 待实机 QA 通过后发布。
- 本版本包含下方两个原 `[未发布]` 区块的全部内容。

---

## [未发布] - 2026-09-15

- 应用、窗口标题及构建产物统一命名为 `MarkdownReader`。
- 重命名 spec、图标和启动图资源，更新 npm 包名及文档引用。
- WebView2 使用 `MarkdownReader/WebView2` 缓存目录；阅读页存储键统一为 `markdownreader-*`，未发布阶段不保留旧名称兼容。

---

## [未发布] - 2026-08-05

### 新增

- Windows 原生文件窗口支持一次复选多个 Markdown。
- 支持从资源管理器拖入 Markdown 文件和文件夹。
- GUI 新增“转换清单”页签，显示预检结果、加入方式、输出位置和逐文件状态。
- 新增转换计划层，在写入前完成递归收集、去重、输出路径计算和冲突检查。
- 支持 Markdown 脚注，以及清单内 `.md` / `.markdown` 跨文档链接到实际 HTML 的重写。
- 新增转换计划、链接、脚注、GUI 契约和端到端转换测试。

### 变更

- 左侧风格选择后会自动切换到对应的右侧预览页。
- 清单外 Markdown 链接保持原值并给出警告，避免生成未经确认的 HTML 地址。
- 多文件和目录转换在生成前阻止扁平输出的同名文件覆盖。
- 转换清单来源统一为“直接加入 / 目录扫描”；“链接依赖”仅保留为未来扩展模型。
- 转换清单改为无表头双行布局；点击文档行可展开完整源路径、输出路径、状态和警告。
- 工作区标签不再随当前页面按比例伸缩；列表和预览保持稳定的主标签，日志正常时静默、出现问题时显示提醒和数量。
- 原生窗口最小宽度与双栏布局统一为 720；转换清单工具栏允许搜索框换行，避免窄窗口裁切导航和搜索控件。
- GUI 启动时内联当前 HTML、CSS 和 JavaScript，避免 WebView2 持久缓存显示旧界面。

---

## [0.9.0-rc] - 2026-07-10

### 当前状态

- 项目完成最终打包前标准回归，进入个人正式版候选 / 内部发布候选阶段。
- 核心转换链路、GUI、三套模板、批量索引和打包方案已基本可用。
- 尚未作为公开正式版发布。

### 新增

- 新增 `templates/index/`，将批量索引页拆分为 `index.html`、`theme.css` 和 `index.js`。
- 新增 `config.json` 作为唯一运行配置文件。
- 恢复 `packaging/` 打包目录、程序图标和启动图资源。
- 放入并验证 `packaging/node/node.exe`，打包后可优先使用内置 Node.js。
- 补充 README 效果截图，包括 GUI、Modern、Office 和 VS Code。

### 变更

- 配置从 `config.toml` 迁移为 `config.json`，不保留 TOML 兼容。
- `core/index_builder.py` 不再内嵌大段 HTML/CSS/JS，改为读取索引模板资源后重新内嵌成单文件 HTML。
- `README.md`、`DESIGN.md`、`ARCHITECTURE.md`、`ROADMAP.md` 和 `AI_Rules.md` 按当前 RC 状态更新。
- 清理历史遗留文件、缓存和生成产物。
- Windows 下调用 Node 子进程时隐藏额外控制台窗口，避免 GUI 转换时弹出 cmd。

### 修复

- 修复 TOC 标题编号分割边界：`8.2.1情况一` 现在会拆分为 `8.2.1` 和 `情况一`，不再误拆为 `8.2.` 和 `1情况一`。
- 标准回归覆盖三套模板、批量索引、中文路径、GUI 非交互 API、打包资源和内置 Node 路径。

### 已知缺口

- 仍需重新打包最终 EXE，并在干净目录完成试跑。
- 需要确认正式版本号和许可证或保留全部权利声明。
- 当前未提供完整 pytest 自动化套件；后续维护阶段建议补回。

---

## [0.6.0] - 2026-07-07

### 新增：阶段 6 - 桌面前端

- 使用 `pywebview` 增加轻量桌面 GUI，基于系统 WebView。
- 新增 `gui/api.py`，以 `BridgeApi` 作为 JavaScript 与 Python 核心之间的轻量
  调用层，不复制业务逻辑。
- 新增 `gui/app.py`，负责窗口创建及 Python 日志到 GUI 的桥接。
- 新增 `gui/assets/index.html`、`gui.css` 和 `gui.js`，提供输入、输出、模板、
  配置、日志和转换后操作。
- 转换时将模板、输出目录和功能选项保存到 `config.toml`。
- 转换成功后可自动使用系统默认浏览器打开 HTML。
- 支持在 Windows、Linux 和 macOS 打开输出目录。
- 在 `config.toml` 与 `core/config.py` 中增加 `auto_open` 配置。

### 变更

- `requirements.txt` 增加 `pywebview>=5.0`。
- README 增加 GUI 使用说明。

### 设计决策

- 选择 pywebview 而不是 Electron，复用系统 WebView2/WebKit，不打包完整浏览器。
- `BridgeApi` 只负责数据传递，所有转换继续委托核心生成流程。
- 阅读生成的 HTML 时使用系统浏览器，不在 GUI 内嵌完整阅读器。
- `WebViewLogHandler` 通过 `window.evaluate_js()` 推送日志，不轮询。
- 文件对话框使用 Python 标准库 `tkinter.filedialog`。

---

## [0.5.0] - 2026-07-07

### 新增：阶段 5 - 渲染生态

- 增加模板继承系统，子模板通过 CSS 层叠覆盖基础模板变量。
- 新增 `templates/default/` 作为完整共享基础模板。
- 新增 `templates/Office/` 正式文档主题。
- 新增 `templates/Vscode/` 技术阅读主题。
- 将 `viewer.js` 移至 `templates/` 根目录，供全部模板共享。
- 将 `print.css` 移至 `templates/` 根目录，供全部模板共享。
- 每个模板通过 `metadata.json` 声明名称、作者、版本、说明和父模板。
- 增加 `resolve_template_chain()`、`load_theme_chain()` 和
  `resolve_template_file()`。
- 无效模板名称通过 `ValueError` 返回明确错误。

### 变更

- `template/` 更名为 `templates/`，用于多模板结构。
- 从 `viewer.css` 中拆出主题变量，形成 `theme.css`。
- 重写模板解析和继承链加载逻辑。
- 生成流程按继承顺序拼接主题 CSS。
- 重新生成 `samples/expected/demo.html`。

### 设计决策

- 基础 `theme.css` 先加载，子模板样式后加载，以 CSS 层叠完成覆盖。
- 所有模板共享 `viewer.js` 与 `print.css`，只改变视觉主题。
- 模板元数据采用声明式 JSON；增加模板无需修改 Python。
- 加载时检测并拒绝循环继承。

### 后续预留

- 企业品牌模板
- 模板资源自动打包与复制
- 第三方模板分发和发现

---

## [0.4.5] - 2026-07-07

### 新增：阶段 4.5 - 质量保障

- 增加 pytest 测试套件，覆盖渲染、目录、Front Matter、CLI 和批量处理。
- 增加渲染器、目录、Front Matter、CLI 和批量处理测试模块。
- 扩展 `samples/demo.md`，覆盖 Front Matter、H1 至 H6、任务列表和长代码块。
- 增加 `samples/expected/demo.html` 作为回归参考输出。
- 新增 `pyproject.toml`，统一配置 pytest、Black 和 Ruff。
- 完善项目 README、配置和开发说明。

### 变更

- Python 源码按 Black 100 字符行宽格式化。
- 使用 Ruff 修复静态检查问题。

### 设计决策

- CLI 测试通过子进程执行，覆盖真实退出码和输出行为。
- 参考 HTML 作为未来输出差异比较基准。
- 工具配置集中在 `pyproject.toml`，不增加分散配置文件。

---

## [0.4.0] - 2026-07-07

### 新增：阶段 4 - 工程化

- 基于 argparse 重写 CLI，支持输出、模板、配置、标题、覆盖和详细日志选项。
- 支持递归扫描目录并批量生成 HTML。
- 自动创建输出目录并保留目录结构。
- 增加包含 `[build]`、`[document]`、`[features]` 的 `config.toml`。
- 增加 Front Matter 解析，支持标题、作者、日期、版本和标签。
- 增加批量文档索引页。
- 支持复制 `images/`、`diagrams/` 和 `assets/` 目录。
- 使用 Python `logging` 代替 `print()`。
- 对缺失文件、权限、解析和配置错误进行明确处理。
- 建立按模板名称解析文件的模板接口。
- 为 Python 3.11 以下环境增加 `tomli` 兼容依赖。

### 变更

- 重写 CLI、配置加载和模板路径解析。
- 将模板文件迁移到 `template/default/`。

### 设计决策

- 配置优先级为 CLI、TOML、默认值。
- `process_single()` 返回 `str | None`，方便调用者判断成功状态。
- 在没有 PyYAML 时使用简单 YAML 解析器。
- 索引页内嵌 CSS，保持单文件原则。
- `template/{name}/` 结构为多模板预留。

### 阶段 5 预留

- GUI 直接调用单文件和批量处理函数。
- 模板参数继续用于多模板。
- 使用 PyInstaller 打包 EXE。

---

## [0.3.0] - 2026-07-07

### 新增：阶段 3 - 易用性

- 增加固定工具栏，提供展开、折叠、自动编号、深色模式和打印操作。
- 增加明暗主题变量、系统主题检测和 `localStorage` 状态保存。
- 使用 CSS 计数器实现 H1 至 H6 自动编号，并避免与人工编号重复。
- 增加可拖动的目录宽度调整条，宽度保存到 `localStorage`。
- 增加工具栏和浮动返回顶部按钮。
- 增加跨平台中文字体栈。
- 改善正文两端对齐、标题间距和引用样式。
- 扩展打印分页规则，并在打印时强制浅色主题。

### 变更

- `viewer.html` 增加工具栏、目录调整条和返回顶部按钮。
- `viewer.css` 增加深色变量、自动编号、工具栏和排版规则。
- `viewer.js` 增加工具栏、深色模式、自动编号、目录宽度和返回顶部模块。
- `print.css` 增加交互控件隐藏和分页规则。
- Demo 增加带编号标题，用于测试自动编号。

### 设计决策

- 所有颜色使用一套 CSS 变量，深色模式只覆盖变量。
- 标题编号由 CSS 计数器完成，不修改正文 DOM。
- JS 为已有人工编号标题添加 `no-autonumber`，防止重复编号。
- 目录调整通过 `--sidebar-width` 变量即时生效。
- 工具栏复用已有折叠逻辑，不另建重复实现。

---

## [0.2.0] - 2026-07-07

### 新增：阶段 2 - 阅读体验

- 增加目录树折叠和展开。
- H1 至 H6 标题均可折叠其下正文。
- 目录与正文折叠状态双向同步。
- 增加图片全屏查看。
- 为代码块增加复制按钮及回退复制方案。
- 使用 `localStorage` 保存和恢复阅读位置。
- 改善标题、段落、代码块、引用和表格排版。

### 变更

- 重写 `viewer.css`，加入折叠、图片查看、复制按钮和排版样式。
- 将 `viewer.js` 重构为模块化 IIFE，同时保留阶段 1 功能。
- 打印时隐藏交互按钮并展开折叠内容。
- 扩展 Demo 的标题层级。

### 设计决策

- 阶段 2 功能全部位于浏览器侧，不修改 Python 生成职责。
- 每项 JavaScript 功能使用独立的 `init*()` 初始化函数。
- 使用 `_isSyncing` 防止目录与正文同步时循环触发。
- 缓存标题下需折叠的元素，避免每次重复遍历 DOM。
- 阅读位置按文档标题分别保存。
- 复制成功只改变按钮文字，不增加额外提示层。

---

## [0.1.0] - 2026-07-07

### 新增：阶段 1

- 建立符合架构文档的项目目录。
- 增加 CLI 入口和 Markdown 转 HTML 流程。
- 增加标题提取和多层目录生成。
- 增加默认配置和模板占位符。
- 增加包含目录与正文的 CSS Grid 阅读器。
- 增加目录跳转和基于 `IntersectionObserver` 的滚动定位。
- 增加打印样式，打印时隐藏目录并扩展正文。
- 增加 Demo 和 Python 依赖声明。

### 核心能力

- Markdown 转单个独立 HTML。
- 根据 H1 至 H6 自动生成嵌套目录。
- 点击目录平滑跳转。
- 正文滚动时自动高亮当前目录项。
- CSS 和 JavaScript 直接内嵌到最终 HTML。
- 打印时隐藏目录并使用完整页面宽度。
- 目录与正文独立滚动。
- CSS 通过变量管理。

### 设计决策

- Python 只负责生成，浏览器负责全部交互。
- 模板使用 `{{TITLE}}`、`{{TOC}}`、`{{CONTENT}}` 占位符。
- 只使用浏览器原生 API。
- 不依赖外部 CSS、JavaScript 或 CDN。
- 渲染、目录和配置模块相互独立。

### 后续阶段预留

- 阶段 2：折叠、代码复制和排版。
- 阶段 3：工具栏、深色模式、搜索和返回顶部。
- 阶段 4：批量生成与跨文档导航。
- 阶段 5：GUI、拖放和 EXE 打包。
