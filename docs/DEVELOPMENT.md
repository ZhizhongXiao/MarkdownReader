# 开发与构建

面向修改源码、运行测试与打包的说明。产品边界见 [设计](DESIGN.md)，分层职责见 [架构](ARCHITECTURE.md)。

## 环境

- Python 3.12.x（`pyproject.toml` 要求 `>=3.12,<3.13`，发布链固定在 3.12）
- Node.js 18+
- Microsoft Edge WebView2 Runtime
- `uv`：创建项目专用 `.venv` 并锁定依赖

```powershell
uv sync
cd node_renderer; npm install; cd ..
cd tests/js; npm ci; cd ..
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
node_renderer/        Node Markdown 渲染器（markdown-it、footnote、texmath、KaTeX）
templates/default/    共享阅读器外壳
templates/Modern|Office|Vscode/   视觉主题（继承 default）
templates/index/      批量索引模板
templates/viewer.js   共享阅读器交互
templates/print.css   共享打印样式
packaging/            打包配置、图标、启动图与发布脚本
samples/              示例与渲染标本（demo.md 与入库的 demo.html）
tests/                自动化测试（tests/js 为 jsdom 层，不进打包）
tools/                辅助脚本（不参与打包）
```

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
