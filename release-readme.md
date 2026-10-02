# MarkdownReader v1.0.1

Windows 便携式 Markdown 转离线阅读 HTML 工具，不需要安装器。

## 下载与运行

- `MarkdownReader-1.0.1-win-x64.exe`：onefile 版本，单个可执行文件。
- `MarkdownReader-1.0.1-portable-win-x64.zip`：onedir 便携版本，解压后运行 `MarkdownReader.exe`。
- 需要 Windows 10/11（64 位）与 Microsoft Edge WebView2 Runtime；Python、Node.js 和渲染依赖已内置。

## 使用

添加或拖入 `.md` / `.markdown` 文件或文件夹，选择输出目录，并按需勾选要随 HTML 携带的外置主题，然后开始转换。每份 HTML 都包含 Modern、Office 和 VS Code 三套内置主题；阅读时可切换主题与明暗模式。

阅读器支持目录导航与折叠、阅读位置恢复、代码复制、公式、脚注、图片灯箱缩放、批量索引与打印。生成的 HTML 无需服务器；本地图片和阅读器资源会尽可能内嵌，以便离线阅读。

## 注意事项

- 同名输出 HTML 会被覆盖。
- 网络图片及源文档中的原始 HTML 资源仍可能引用外部地址；无网络时转换继续，并保留无法获取的原始 URL。
- 打印分页与字体替换取决于浏览器及本机环境。
- onefile 用户数据位于 `%LOCALAPPDATA%\MarkdownReader\`；onedir 数据位于应用目录的 `data\`。设置页显示具体路径。
- 可使用随附的 `SHA256SUMS.txt` 核验 EXE 与便携 ZIP。

暂未选择开源许可证，代码与资源保留全部权利。
