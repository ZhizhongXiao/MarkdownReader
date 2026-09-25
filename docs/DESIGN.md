# 设计

## 定位

MarkdownReader 把 Markdown 文件转换成可离线阅读的独立 HTML，面向长文阅读、左侧目录导航、
打印或导出 PDF，以及多文件资料索引。生成的 HTML 是核心交付物，GUI 与 EXE 只是提供入口。

它不是 Markdown 编辑器、不是实时预览工具、不是在线文档服务、不是静态网站生成器，也不是协作平台。

## 设计原则

### 离线优先

生成的 HTML 自包含：不依赖服务器、CDN 或网络连接。

### 阅读优先

功能围绕阅读、导航与打印，不引入编辑、同步、协作等非核心能力。

### 职责分离

Python 负责调度与组装，Node 负责 Markdown 渲染，浏览器负责阅读交互：

```text
Markdown → Python 调度 → Node 渲染 → 模板组装 → 浏览器阅读
```

### 单文件交付

每个 Markdown 输出一个独立 HTML，索引页同理；CSS 与 JavaScript 在生成时内嵌。

### 模板可维护

阅读器外壳由 `default` 模板提供，主题只覆盖视觉样式，不复制交互逻辑。

## 模板体系

```text
viewer/viewer.html    阅读器外壳：工具栏、目录、正文容器
viewer/css/layout.css 共享布局与组件样式（只消费主题变量）
viewer/css/print.css  共享打印样式
viewer/js/*.js        阅读器交互模块（manifest.json 声明加载顺序，装配时拼成一个脚本）
themes/builtin/base/  基础主题 token（调色板、字体、布局尺寸），hidden，不可选
themes/builtin/modern/     通用阅读主题
themes/builtin/office/     类 Word 正式文档与打印主题
themes/builtin/vscode/     编辑器预览风格的技术主题
templates/index/      批量索引页（index.html + theme.css + index.js，生成时内嵌；独立表面）
```

三个主题都继承 `default`；索引页与阅读页是两套独立的单文件产物。各主题的视觉约定见各自的 README。

## GUI 的边界

GUI 使用 pywebview，只作为桌面入口：文件与目录选择、Windows 复选与拖入、转换清单与预检、
输出目录与模板选择、转换选项、静态模板预览、日志展示，以及调用核心转换流程。

GUI 不负责 Markdown 解析、目录生成、正文渲染与阅读器交互逻辑；配置写在 `config.json`。

## 打印

打印是一等能力：隐藏工具栏、目录与返回顶部等交互控件，保持白底，尽量减少标题孤行、
图片截断、代码块截断与表格截断。Office 是打印优先主题；Modern 与 VS Code 保证正常打印，
但不追求与 Word 逐页一致。

## 依赖与分发

源码运行需要 Python 3.12.x、Node.js 18+、pywebview 与 Node 渲染依赖。面向用户的发布包内置
Python 运行时、Node.js 与渲染依赖，只使用内置 Node（缺失即视为打包物损坏），不增加安装器、
后台更新服务或自更新器；配置与日志写在 EXE 同级的 `config.json` 与 `MarkdownReader.log`。

## 不做

Markdown 编辑、实时编辑预览、云同步、多人协作、数据库、Web 服务、插件市场与复杂网站生成。
后续扩展围绕阅读器生成、模板与打印体验展开。
