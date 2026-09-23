# 项目命名说明

## 当前名称

| 用途 | 名称或路径 |
| --- | --- |
| 项目名称、应用标题、文档正文 | `MarkdownReader` |
| 当前构建产物 | `dist/MarkdownReader.exe` |
| PyInstaller 构建配置 | `packaging/MarkdownReader.spec` |
| Windows 图标 | `packaging/assets/MarkdownReader.ico` |
| 启动图文件 | `packaging/assets/MarkdownReader_splash.png` |
| WebView2 缓存目录 | `%LOCALAPPDATA%\MarkdownReader\WebView2` |
| npm 包标识 | `markdownreader-node-renderer` |

项目名称使用大写 M 和 R。npm 包标识及自动生成的标题锚点使用全小写形式。
模板目录按实际路径写为 `templates/Modern/`、`templates/Office/`、`templates/Vscode/`；配置中的模板 ID 仍是 `modern`、`office`、`vscode`。

## 内部标识与构建产物

- 阅读器浏览器存储键统一使用 `markdownreader-*`，包括主题、折叠、阅读位置和目录宽度。项目尚未发布，不读取或迁移旧名称存储键。
- 配置文件继续使用 `config.json`。
- 项目尚未发布，`dist/` 仅保留当前 `MarkdownReader.exe` 和运行配置，旧版 EXE 可移除。

后续项目名称统一使用 `MarkdownReader`，不要新增旧名称别名或兼容分支。
