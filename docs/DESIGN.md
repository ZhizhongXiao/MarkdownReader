# 设计

## 定位

MarkdownReader 把 Markdown 文件转换成可离线阅读的独立 HTML，面向长文阅读、左侧目录导航、
打印或导出 PDF，以及多文件资料索引。生成的 HTML 是核心交付物，GUI 与 EXE 只是提供入口。

它不是 Markdown 编辑器、不是实时预览工具、不是在线文档服务、不是静态网站生成器，也不是协作平台。

## 设计原则

### 离线优先

生成的 HTML 无需 Web 服务。阅读器、主题、交互脚本及可读取的本地资源会尽可能内嵌；如果转换时无法获取远程资源，文档会保留原 URL，因此这类文档仍可能需要网络。

### 阅读优先

功能围绕阅读、导航与打印，不引入编辑、同步、协作等非核心能力。

### 职责分离

Python 负责调度与组装，Node 负责 Markdown 渲染，浏览器负责阅读交互：

```text
Markdown → Python 调度 → Node 渲染 → 模板组装 → 浏览器阅读
```

### 单文件交付

每个 Markdown 输出一个独立 HTML，索引页同理；CSS 与 JavaScript 在生成时内嵌。

### 阅读器与主题分离

Viewer 负责阅读器 DOM 与交互，Theme 只负责视觉样式。二者通过共享资产层组合，不复制交互逻辑。

## 阅读器与主题体系

```text
viewer/viewer.html    阅读器外壳：工具栏、目录、正文容器
viewer/css/layout.css 共享布局与组件样式（只消费主题变量）
viewer/css/print.css  共享打印样式
viewer/js/*.js        阅读器交互模块（manifest.json 声明加载顺序，装配时拼成一个脚本）
themes/builtin/base/  基础主题 token（调色板、字体、布局尺寸），全局回落，不可选择
themes/builtin/modern/     通用阅读主题
themes/builtin/office/     类 Word 正式文档与打印主题
themes/builtin/vscode/     编辑器风格的技术主题
themes/template/      外置主题开发模板（随包发布；导出 → 编辑 → 导入）
assets/themes/external/  用户安装的外置主题（用户资产，永不随包）
templates/index/      批量索引页（独立表面）
```

每份生成的阅读文档都携带 base、Modern、Office 和 VS Code；阅读者在 HTML 中选择内置主题，偏好保存在该 HTML 的
localStorage。主页面的内置主题预览只存在于本次 GUI 会话；外置主题复选框则决定本次转换要携带哪些已安装主题，
选择保存在 MarkdownReader 配置中。索引页与阅读页是两套独立的单文件产物。

## GUI 的边界

GUI 使用 pywebview，只作为桌面入口：文件与目录选择、Windows 复选与拖入、转换清单与预检、
输出目录、转换选项、会话级主题预览、外置主题携带选择、日志展示，以及调用核心转换流程。

GUI 不负责 Markdown 解析、目录生成、正文渲染与阅读器交互逻辑。主题区域提供会话级视觉预览；转换参数不包含
内置主题选择。初始阅读主题 fallback 由 bridge 内部的 `BOOTSTRAP_TEMPLATE = "modern"` 决定，不属于用户配置。

## 打印

打印是一等能力：隐藏工具栏、目录与返回顶部等交互控件，保持白底，尽量减少标题孤行、
图片截断、代码块截断与表格截断。Office 是打印优先主题；Modern 与 VS Code 保证正常打印，
但不追求与 Word 逐页一致。

## 依赖与分发

源码运行需要 Python 3.12.x、Node.js 18+、pywebview 与 Node 渲染依赖。面向用户的发布包内置
Python 运行时、Node.js 与渲染依赖，只使用内置 Node（缺失即视为打包物损坏），不增加安装器、
后台更新服务或自更新器。用户数据按运行方式集中到统一数据根：源码运行使用 `<repo>/.runtime/`，
onedir 使用 `<app>/data/`，onefile 使用 `%LOCALAPPDATA%/MarkdownReader/`；设置、外置主题与运行数据
分别归入 `profile/`、`assets/` 与 `runtime/`。

## 不做

Markdown 编辑、实时编辑预览、云同步、多人协作、数据库、Web 服务、插件市场与复杂网站生成。
后续扩展围绕阅读器生成、模板与打印体验展开。
