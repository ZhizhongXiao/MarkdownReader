# 打包与发布

把源码构建成 Windows 便携产物，并给出发布流程。使用 `packaging/MarkdownReader.spec`，
默认产物是 `dist/MarkdownReader.exe`（onefile）。

## 产物形态

- **onefile**（默认）：单个 EXE，启动时需要释放运行时，杀软扫描与临时目录占用相对明显。
- **onedir**：设置 `MR_BUILD_MODE=onedir` 后重新构建，得到目录树；启动更快、更少被拦，代价是要带上整个目录。

两种形态都由 `packaging/validate_release.py` 校验，发布时都给。项目保持无安装器的便携形态，
不引入安装器、后台更新服务、自更新器或增量补丁。资源随 EXE 发布：即使只改一处样式，也重新构建整个产物，
不在用户目录里热替换内部资源。

## 构建

```powershell
uv lock --check
uv sync --locked --extra build
python -m PyInstaller --clean --noconfirm --workpath "packaging\.pyinstaller-build" --distpath "dist" packaging\MarkdownReader.spec
```

构建缓存位于 `packaging/.pyinstaller-build/`，完成后可安全删除；`--clean` 会清理缓存与本次 workpath。
需要完全排除旧产物影响时先删除 `dist/`。

打包内容：GUI 静态资源、阅读器资产（`viewer/`）、内置主题（`themes/builtin/`）、批索引页模板
（`templates/index/`）、v2 renderer 载荷（`renderer/dist/`）、Node 渲染脚本与依赖、内置 Node 运行时、
启动图与程序图标。

## v2 renderer 载荷

发布包默认使用 v2 renderer，因此必须带上：

```text
renderer/dist/renderer.cjs
renderer/dist/katex/
renderer/dist/mermaid/
```

它们是 gitignored 构建产物（`cd renderer; npm ci; npm run build`）。`packaging/release_freeze.py`
在 PyInstaller 之前自动执行这两步，spec 在缺少它们时直接让构建失败。构建期还会用
`packaging/node/node.exe` 对 v1 与 v2 各做一次冒烟：既要证明内置 Node 能跑，也要证明即将打包的
`renderer/dist` 与即将打包的 `node.exe` 真的能合作。

`renderer/node_modules/`、`renderer/src/`、`renderer/vendor/` 是构建期输入，不进发布包。
`node_renderer/`（脚本 + 依赖）继续随包发布，它是 v1 回退路径。

## 内置 Node

正式包只使用内置 Node，缺失即视为打包物损坏并在启动时报错，不会回退到系统 `PATH`。约定路径：

```text
packaging/node/node.exe
```

把 Windows x64 zip 版 Node.js 解压后放入 `packaging/node/`，确认 `node.exe` 存在再构建。
该目录不进版本库，重新检出源码后需自行准备；spec 在其缺失时直接让构建失败。
源码运行不受此限制，但仍需本机 Node.js。

## 运行时行为

- `config.json` 与 `MarkdownReader.log` 写在 EXE 同级目录。
- 只读资源从 PyInstaller 临时目录加载；WebView2 数据位于 `%LOCALAPPDATA%\MarkdownReader\WebView2`。
- 需要 Microsoft Edge WebView2 Runtime（强制 `edgechromium`，不降级到 MSHTML）。

启动图与图标：

```text
packaging/assets/MarkdownReader_splash.png
packaging/assets/MarkdownReader.ico
```

替换后必须重新构建。

## 校验与发布

```powershell
python packaging/validate_release.py --mode both --wait 20   # 存在性、体积、资源与启动存活
python packaging/release_freeze.py --check-only              # 版本一致性与实机验收证据
python packaging/release_freeze.py --tag                     # 重建产物、写校验和与记录、打并推送 tag
```

`release_freeze.py` 要求工作区干净、HEAD 与 `origin/main` 一致，并从 `docs/QA-CHECKLIST.md` 读取验收结果：
条目全部勾选且结论包含 `QA 结论：通过` 才允许打 tag。发布物为 EXE、便携 ZIP、`SHA256SUMS.txt`
与 `release-record-<版本>.md`。

`--qa-record` 默认指向 `docs/QA-CHECKLIST.md`；实机验收记录必须与**当前 production renderer**
对应（v2 cutover 之后的记录不能沿用 v1 时代的勾选），因此切换 production renderer 时要指向对应
的那一份记录文件。
