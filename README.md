# MarkdownReader

MarkdownReader 是一个离线 Markdown 转 HTML 阅读器生成工具：把 Markdown 文件转换成适合长文阅读、
目录导航与打印的独立 HTML，Windows 便携使用，不需要安装器。

## 能做什么

- 单文件、Windows 原生多选与文件夹批量转换，支持从资源管理器拖入文件或目录。
- 三套内置阅读主题：Modern（通用阅读）、Office（正式文档与打印）、VS Code（技术文档）；每份 HTML 都携带三套，阅读时可切换。
- 生成的 HTML 单文件自包含：阅读器样式、脚本、目录、公式样式与字体都在文件内；不使用 CDN、
  不需要服务器；本地图片内嵌，离线可直接打开。
- 阅读器交互：目录跳转与滚动定位、目录与正文折叠、阅读位置恢复、代码复制、
  图片灯箱（滚轮缩放到 6 倍）、主题切换、明暗模式、自动编号，以及白纸 + 跟随正文主题框线的打印。
- 批量转换可生成索引页，并保留源目录结构。

具体的写法范围见 [兼容范围](docs/MARKDOWN.md)。

## 开始使用

1. 下载 `MarkdownReader-1.0.0-rc1-win-x64.exe` 放入可写目录后双击运行；或解压便携版 ZIP，运行其中的 EXE。
2. 添加 Markdown 文件或文件夹，选择输出目录与主题。
3. 点「开始转换」，完成后用浏览器打开生成的 HTML。

需要 Windows 10 / 11（64 位）与 Microsoft Edge WebView2 Runtime；EXE 已内置 Python、Node.js 与渲染依赖。
逐步操作、输出规则与常见问题见 [使用说明](docs/USAGE.md)。

## 效果与示例

- 渲染标本：[samples/demo.md](samples/demo.md)
- 对应的生成结果：[samples/demo.html](samples/demo.html)（由当前源码生成，测试会校验两者一致）

## 文档

| 文档 | 内容 |
| --- | --- |
| [使用说明](docs/USAGE.md) | 操作流程、输出规则、设置与日志、常见问题 |
| [兼容范围](docs/MARKDOWN.md) | 支持的 Markdown 与原始 HTML 写法、明确不支持的部分、图片处理 |
| [设计](docs/DESIGN.md) | 产品定位与设计原则 |
| [架构](docs/ARCHITECTURE.md) | 分层结构与各层职责 |
| [开发与构建](docs/DEVELOPMENT.md) | 环境、测试、目录、命名约定、打包与发布 |
| [路线图](docs/ROADMAP.md) | 当前状态与下一步方向 |
| [更新日志](docs/CHANGELOG.md) | 各版本变更记录 |
| [实机验收清单](docs/QA-CHECKLIST.md) | 1.0.0-rc1 的实机验收记录（历史证据） |
| [打包说明](packaging/README.md) | 构建形态与发布流程细节 |

## 环境与主要限制

- 面向 Windows 10 / 11（64 位）与 Chromium 内核浏览器；打印以 Microsoft Edge 为主要参考。
- 打印分页与字体替换取决于浏览器和本机环境，不追求与 Word 逐页一致。
- 原始 HTML 的复杂样式由浏览器解释，不保证所有网页级布局都适合打印。
- 部分主题依赖系统安装的 `Source Han Sans SC`（未随 HTML 内嵌），缺少时由系统字体回退决定实际显示；
  Modern 与 VS Code 还把它用作代码字体，因此代码不保证等宽。
- 网络图片与原始 HTML 中的资源引用保持源文档行为，需要相应的网络或文件访问。

## 当前状态

1.0.0-rc1 已完成 33 项实机验收并通过，结论与测试机器信息记录在 [实机验收清单](docs/QA-CHECKLIST.md)；
发布物是 `dist/` 下的 EXE、便携 ZIP、`SHA256SUMS.txt` 与构建记录。升为 1.0.0 待许可证与正式发布决定。

项目面向个人使用与内部发布；暂未选择开源许可证，代码与资源保留全部权利。
