# MarkdownReader Windows 打包

项目名称、应用窗口和构建产物统一为 `MarkdownReader`，使用 `packaging/MarkdownReader.spec` 生成 `dist/MarkdownReader.exe`。

## 便携发布定位

MarkdownReader 保持“下载一个 EXE 即可运行”的无安装器便携形态。打包升级只改善依赖锁定、构建隔离、WebView2 失败提示和发布可追溯性，不改为安装器；`onedir` 作为性能与 Defender 友好的备选形态由同一 spec 支持。

项目进入以修复和微调为主的维护期：预计仍会修改 CSS、模板、兼容性处理和少量内部逻辑，但不再以增加大型功能为目标。因此应保留稳定、可复现的完整重打包流程；不增加安装器、后台更新服务、自更新器或二进制增量补丁。当前尚未发布，整理阶段只保留最新完整 EXE，旧构建可移除。正式发布后的版本留存策略届时再确定。

推荐目标：

- 使用 `uv` 管理项目专用 `.venv` 和 `uv.lock`，不再依赖全局 Python 包集合；
- 在 `pyproject.toml` 声明运行依赖，在 `build` extra 声明 PyInstaller 与 Pillow，并用 `uv.lock` 锁定解析结果；
- 保留 PyInstaller `onefile`、`windowed`、启动图、图标和内置 Node.js；
- 将 `MarkdownReader.spec` 的 `upx` 改为 `False`，不使用 UPX；
- 继续强制使用 `edgechromium`，不降级到 MSHTML；
- 启动前检测 WebView2 Runtime；缺失时通过原生 Windows 对话框说明原因并提供官方安装入口，不由便携工具静默安装系统组件；
- 在无 Python、无系统 Node.js、普通用户权限和中文/空格路径中验证最终 EXE。

下列方式已落地：`pyproject.toml` 声明分层依赖，`uv.lock` 锁定解析，spec 支持双形态并在构建前做真实渲染器自检。推荐构建入口：

```powershell
uv lock --check
uv sync --locked --extra build
uv run --locked --extra build python -m PyInstaller `
  --clean --noconfirm `
  --workpath "packaging\.pyinstaller-build" `
  --distpath "dist" `
  packaging\MarkdownReader.spec
```

目标机器不需要 Python、pip、uv、虚拟环境、Node.js 或 npm 依赖。WebView2 Runtime 仍由 Windows 提供；便携 EXE 只负责检测和给出明确提示。

若内置 Node 导致单文件启动释放时间、Defender 扫描或临时目录占用不可接受，可改用同一 spec 产出 onedir 目录树：设置 `MR_BUILD_MODE=onedir` 后重新打包即可（默认仍为 onefile）。两种形态都由 `packaging/validate_release.py` 校验。

CSS、模板等资源目前随 EXE 一起发布；即使只改一处样式，也应重新生成并验证整个 EXE，不在用户目录中热替换内部资源。这样可以避免“程序版本与资源版本不一致”，也无需设计资源迁移和在线更新协议。

## 当前构建命令

先在项目虚拟环境安装运行依赖和构建工具，并在 `node_renderer` 中执行 `npm ci`。`Pillow`（缩放启动图）已随 `build` extra 声明：

```powershell
uv sync --locked --extra build
```

在项目根目录构建单文件 Windows EXE：

```powershell
python -m PyInstaller --clean --noconfirm --workpath "packaging\.pyinstaller-build" --distpath "dist" packaging\MarkdownReader.spec
```

该命令使用项目内专用构建缓存：

```text
packaging/.pyinstaller-build/
```

这样可以避免继续使用 PyInstaller 默认的 `build/` 目录。如果默认 `build/` 曾经出现 `WinError 5` 或文件占用问题，通常不需要再处理旧目录，直接使用上面的命令即可。

默认产物为：

```text
dist/MarkdownReader.exe
```

`--clean` 会清理 PyInstaller 缓存和本次指定的 workpath。最终发布前如需完全排除旧产物影响，可以手动删除 `dist/` 后重新打包。`packaging/.pyinstaller-build/` 只是中间缓存，打包完成后可以安全删除。

打包内容包括：

- GUI 静态资源
- 全部阅读器模板
- Node 渲染脚本及 npm 依赖
- 内置 Node.js 运行时
- PyInstaller 启动图
- Windows 程序图标

## 内置 Node.js

为了让普通用户无需再安装 Node.js，正式发布包应内置 Windows 便携版 Node.js。

约定目录为：

```text
packaging/node/node.exe
```

推荐做法：

1. 下载 Windows x64 zip 版 Node.js。
2. 解压后将包含 `node.exe` 的目录内容复制到 `packaging/node/`。
3. 确认 `packaging/node/node.exe` 存在。
4. 再运行 PyInstaller 打包命令。

`packaging/MarkdownReader.spec` 会把 `packaging/node/` 打入发行包，并在其缺失时**直接让构建失败**。
运行时只使用内置的 `node/node.exe`；正式包缺少它即视为打包物损坏并在启动时报错，**不会**回退到系统 `PATH`。源码运行不受此限制。

本地构建已准备此运行时，但它被 Git 忽略。重新检出源码后，构建前需自行准备并确认以下路径存在：

```text
packaging/node/node.exe
```

因此：

- 面向普通用户发布时：建议内置 Node.js，用户无需额外安装。
- 开发者源码运行时：仍需本机安装 Node.js，并运行 `cd node_renderer && npm install`。

Windows 下 Node 子进程会以隐藏窗口方式运行，避免 GUI 转换过程中弹出额外 cmd 窗口。

运行时：

- `config.json` 在 `MarkdownReader.exe` 同级目录读取和写入
- 打包的只读资源从 PyInstaller 临时目录加载
- WebView2 数据保存在 `%LOCALAPPDATA%\MarkdownReader\WebView2`
- 阅读器使用统一的 `markdownreader-*` 浏览器存储键

启动图和图标资源位于：

```text
packaging/assets/MarkdownReader_splash.png
packaging/assets/MarkdownReader.ico
```

替换资源后需要重新打包，现有 EXE 不会自动更新。

## 发布前检查

最终发布前建议至少确认：

- `uv lock --check` 通过，`uv.lock` 与 `pyproject.toml` 一致。
- 发布解释器为 3.12.x（`requires-python = ">=3.12,<3.13"`，`.python-version` = 3.12），并在发布记录里写明实际补丁版本。
- `dist/MarkdownReader.exe` 可在干净目录启动。
- 目标目录和目标机器不需要 Python、uv 或虚拟环境。
- 没有系统 Node.js 时仍优先使用内置 `node/node.exe`。
- 当前强制使用 WebView2；缺失 Runtime 时的原生检测和安装提示属于待实施方案，发布前需验证目标机器已安装 Runtime。
- `config.json` 在**首次保存设置 / 首次成功进入转换流程时**写入 EXE 同级目录；单纯启动不会创建它。
- 单文件转换、文件夹批量转换、索引页和三套模板均可用。
- 转换过程中不会弹出额外命令行窗口。
- 发布记录包含 Python、uv、PyInstaller、pywebview、Node.js 版本，`uv.lock` 哈希和 EXE SHA-256。
- 运行 `python packaging/validate_release.py --mode both`：产物存在、体积合理、onedir 携带 Node 与渲染资源、两种形态都能启动并在启动校验通过后存活。
- 当前产物统一为 `dist/MarkdownReader.exe`，旧版 EXE 可移除；保留已有的 `config.json`。

