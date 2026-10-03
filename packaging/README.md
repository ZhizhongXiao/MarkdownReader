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
（`templates/index/`）、v2 renderer 载荷（`renderer/dist/`）、内置 Node 运行时、
启动图与程序图标。

## v2 renderer 载荷

v2 是当前唯一支持的 renderer，因此每个发布包都必须带上：

```text
renderer/dist/renderer.cjs
renderer/dist/katex/
renderer/dist/mermaid/
```

它们是 gitignored 构建产物（`cd renderer; npm ci; npm run build`）。`packaging/release_freeze.py`
在 PyInstaller 之前自动执行这两步，spec 在缺少它们时直接让构建失败。构建期还会用
`packaging/node/node.exe` 对 v2 renderer 做一次冒烟，证明即将打包的 artifact 与 Node runtime 能合作。

`renderer/node_modules/`、`renderer/src/`、`renderer/vendor/` 是构建期输入，不进发布包。

## 内置 Node

正式包只使用内置 Node，缺失即视为打包物损坏并在启动时报错，不会回退到系统 `PATH`。约定路径：

```text
packaging/node/node.exe
```

把 Windows x64 zip 版 Node.js 解压后放入 `packaging/node/`，确认 `node.exe` 存在再构建。
该目录不进版本库，重新检出源码后需自行准备；spec 在其缺失时直接让构建失败。
源码运行不受此限制，但仍需本机 Node.js。

## 运行时行为

- 用户数据按运行方式集中到一个数据根：源码运行 `<仓库>/.runtime/`、onedir `<应用目录>/data/`、
  onefile `%LOCALAPPDATA%\MarkdownReader/`；设置、外置主题与运行数据分别在 `profile/`、`assets/`、
  `runtime/` 下（日志与 WebView2 profile 属于运行数据，因此都在 `runtime/`）。
- 只读资源从 PyInstaller 临时目录加载；需要 Microsoft Edge WebView2 Runtime（强制 `edgechromium`，
  不降级到 MSHTML），它是系统前置，不是随包内容。
- onedir 的「删除整个应用目录即完整移除」因此成立；onefile 的数据与 EXE 分离，移动 EXE 不丢设置，
  设置页另提供「移除 MarkdownReader 用户数据并退出」。

启动图与图标：

```text
packaging/assets/MarkdownReader_splash.png
packaging/assets/MarkdownReader.ico
```

替换后必须重新构建。

## 校验与发布

```powershell
python packaging/validate_release.py --mode both --wait 20 --dist-dir "output/candidate/dist"
python packaging/release_freeze.py --check-only
python packaging/release_freeze.py --tag --artifact-dir "output/candidate/dist"
```

`release_freeze.py` 要求工作区干净、HEAD 与 `origin/main` 一致，并读取**当前发布对应的**验收记录：
记录里的 `QA identity` 块（`version` / `production_renderer` / `shapes` / `platform`）必须与当前版本和
当前 production renderer 匹配，条目全部勾选且结论包含 `QA 结论：通过`，才允许打 tag。发布物为 EXE、
便携 ZIP、`SHA256SUMS.txt` 与 `release-record-<版本>.md`。

记录默认**不按固定路径**查找：`release_freeze.py` 扫描 `docs/QA-CHECKLIST*.md`，用身份块选出唯一匹配的
那一份；0 条、多条、或候选里有格式损坏的身份块都直接拒绝并说明原因。`--qa-record` 可以显式指定任意路径，
但同样必须通过身份校验 —— 显式指定是选择文件，不是豁免检查。`docs/history/releases/1.0.0-rc1/QA-CHECKLIST.md` 是 v1 时代的历史记录，
没有身份块，因此永远不会被当成当前 release 的证据。

`--tag` 必须指向验收清单绑定的候选 `dist/`。门禁会核对清单、候选 manifest 与 EXE / ZIP 的 SHA-256，
重新运行两种形态的隔离启动校验，并在确认校验前后哈希不变后复用原文件打 tag；不会在验收后重新构建或重压 ZIP。
候选构建之后只允许更新验收记录和发布门禁/说明文件；任何应用源码变化都会使候选失效，必须重新构建并重新验收。
无 `--tag` 的构建仍可用于本机打包检查，但不能代替被验收的候选产物。

校验过程本身也是隔离的：`validate_release.py` 在沙箱副本上运行 onedir 候选，并给 onefile 运行注入临时的
`LOCALAPPDATA` / `APPDATA`，所以候选树与开发机的真实 profile 都不会被校验改动。如果
候选 `MarkdownReader/` 里已经出现 `data/`（说明有人就地运行过候选），候选绑定门禁会拒绝发布，
而不是把用户数据从压缩包里过滤掉。
