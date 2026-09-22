# MarkdownReader v1.0.0-rc1

Windows 便携式 Markdown 转 HTML 阅读器生成工具，无需安装器。

## 下载与运行

1. 下载 `MarkdownReader-1.0.0-rc1-win-x64.exe`，放入可写目录后双击运行。
2. 也可以使用 `MarkdownReader-1.0.0-rc1-portable-win-x64.zip`：解压后运行其中的 EXE。ZIP 为便携备选形态（onedir），启动更快、更不容易被杀软拦截，代价是需要保留整个目录。
3. 需要 Windows 10/11（64 位）及 Microsoft Edge WebView2 Runtime。
4. 已内置 Python、Node.js 和渲染依赖，无需另行安装开发环境。

## 使用

添加或拖入 `.md` / `.markdown` 文件、文件夹，选择输出目录及 Modern、Office 或 VS Code 模板，点击“开始转换”。完成后点击“打开 HTML”阅读。

支持目录导航、折叠、代码复制、公式、脚注、明暗模式和打印；批量转换可生成索引并保留目录结构。设置在首次保存时写入 EXE 同级目录的 `config.json`（单纯启动不会创建）。

## 注意事项

- 同名输出 HTML 会被覆盖。
- 阅读器样式、脚本和公式资源内置于 HTML；标准 Markdown 引用的本地图片会自动内嵌为 data URI，网络图片与原始 HTML 中的资源仍按源文档引用，需保证输出环境能访问它们。
- 打印分页和字体效果取决于浏览器及本机环境。
- 本版本通过 97 项自动化测试（含三套行为契约层与 harness 自检），并由 `packaging/validate_release.py` 对打包产物做启动与资源校验；真实 GUI、打印与目标机器表现仍需实机验收。

本次发布统一项目名称、更新示例文档和明暗模式截图。可使用随附的 `SHA256SUMS.txt` 核验发布物（EXE 与可选 ZIP 均在其内）。

暂未选择开源许可证，代码与资源保留全部权利。
