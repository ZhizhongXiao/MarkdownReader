# MarkdownReader 架构文档

版本：1.0 发布候选

---

## 1. 总览

MarkdownReader 由四层组成：

```text
pywebview GUI
    ↓
Python 核心调度层
    ↓
Node Markdown 渲染层
    ↓
HTML / CSS / JS 阅读器模板
```

核心原则：

- Python 负责流程和文件组织。
- Node 负责 Markdown 到 HTML 片段的渲染。
- 浏览器负责阅读器运行时交互。
- 模板负责最终视觉和打印表现。

---

## 2. 当前目录结构

```text
core/                 Python 核心流程
gui/                  pywebview 桌面 GUI
node_renderer/        Node Markdown 渲染服务
templates/            阅读器模板和索引模板
packaging/            PyInstaller 打包配置与图标资源
samples/              Markdown 示例（输出本地生成，不纳入版本控制）
tools/                本地辅助脚本（不参与打包）
docs/                 设计、架构、路线图、更新日志和截图
tests/                pytest 自动化测试
config.json           GUI 保存的运行配置
main.py               GUI 启动入口
```

`tests/` 包含当前 pytest 自动化测试，覆盖转换计划、跨文档链接与脚注渲染、
批量转换集成、demo 生成结构、转换边界契约、TOC 标题契约、图片内嵌契约以及 GUI 资源/契约。渲染相关测试需要本机 Node.js 与
`node_renderer/node_modules`。viewer 状态契约另有独立测试层：`tests/js/`（jsdom + Node 内置 test runner，由 `tests/test_viewer_state_contract.py` 调用）。该层只用于测试、不进打包，未安装 jsdom 时对应模块显式 skip 而非静默通过。自动化测试目前不覆盖 GUI 运行时交互、
浏览器打印和打包后 EXE 的完整实机行为。测试不长期保留已知缺陷：契约修复后即摘除对应的 `xfail` 标记。

---

## 3. Python 核心层

主要模块：

```text
core/config.py          配置、路径、模板继承解析
core/converter.py       单文件和批量转换流程
core/conversion_plan.py 转换前输入展开、输出路径和冲突预检
core/renderer_node.py   Node 渲染桥接
core/toc.py             TOC HTML 生成（标题由 Node 渲染器提供）
core/index_builder.py   批量索引页生成
core/fm.py              Front Matter 解析
core/logger.py          日志配置
```

Python 层负责：

- 读取输入文件
- 收集 Markdown 文件
- 在写入前建立源 Markdown 到输出 HTML 的完整映射
- 检测扁平输出的同名冲突
- 调用 Node 渲染器
- 接收 HTML 片段与标题列表
- 生成 TOC
- 拼装模板
- 写出 HTML
- 生成批量索引

### 转换清单来源模型

转换计划中的每篇文档记录其纳入方式。当前正式支持：

- `selected` → **直接加入**：用户通过 Windows 文件窗口或拖拽直接加入单个文件。
- `directory` → **目录扫描**：用户选择或拖入文件夹后，由递归扫描发现。

`dependency` → **链接依赖** 仅作为未来扩展标识保留。当前“显式转换清单”模式不会
自动沿跨文档链接扩大转换范围，也不应在 GUI 中产生“链接依赖”项目。若以后实现依赖
自动发现，应继续复用转换计划和清单界面，并明确区分用户直接指定的文档与自动加入的
文档。

Python 层不得复制浏览器交互逻辑。

---

## 4. Node 渲染层

位置：

```text
node_renderer/render.js
```

Node 负责：

- Markdown 解析
- 脚注解析
- 按 Python 提供的转换清单重写跨文档 Markdown 链接
- 行内公式和块级公式渲染
- KaTeX CSS 资源内联
- 将可解析的本地 Markdown 图片内嵌为 data URI；网络图片、未知 scheme 与 raw HTML 资源保持源行为
- 输出 HTML 片段、标题信息和渲染资源

Python 通过子进程调用 Node：

```text
Python stdin JSON → Node render.js → stdout JSON → Python
```

源码运行时依赖系统 Node；打包后优先使用内置：

```text
node/node.exe
```

Windows 下调用 Node 子进程时使用 `CREATE_NO_WINDOW`，避免 GUI EXE 转换过程中弹出额外控制台窗口。

---

## 5. 模板层

阅读器模板：

```text
templates/default/viewer.html
templates/default/viewer.css
templates/default/theme.css
templates/viewer.js
templates/print.css
```

个性化模板：

```text
templates/Modern/theme.css
templates/Office/theme.css
templates/Vscode/theme.css
```

索引模板：

```text
templates/index/index.html
templates/index/theme.css
templates/index/index.js
```

模板继承由 `metadata.json` 声明。基础与子模板的 `theme.css` 按继承链顺序加载，
子模板通过 CSS 层叠覆盖基础变量和规则；`viewer.js` 为所有模板共享，不在子模板中复制。

---

## 6. 浏览器交互层

共享阅读器脚本：

```text
templates/viewer.js
```

负责：

- TOC 点击跳转
- Scroll Spy
- TOC 折叠
- 正文折叠
- 展开/折叠按钮
- 自动编号
- 明暗模式
- 图片放大
- 代码复制
- 表格和代码块滚动包装
- 打印触发（`window.print()`）；打印版式由 `print.css` 的 `@media print` 提供

JavaScript 不解析 Markdown。

---

## 7. GUI 层

GUI 文件：

```text
gui/app.py
gui/api.py
gui/assets/index.html
gui/assets/gui.css
gui/assets/gui.js
```

GUI 通过 `BridgeApi` 调用核心转换函数。GUI 不生成 Markdown HTML，也不复制 TOC、折叠或阅读器逻辑。

GUI 配置写入：

```text
config.json
```

---

## 8. 打包层

打包文件：

```text
packaging/MarkdownReader.spec
packaging/assets/MarkdownReader.ico
packaging/assets/MarkdownReader_splash.png
```

PyInstaller 打包内容：

- Python 程序
- GUI 静态资源
- templates
- node_renderer
- 便携版 Node.js
- 图标和启动图

---

## 9. 配置

主配置文件：

```text
config.json
```

分区：

```json
{
  "build": {},
  "document": {},
  "features": {}
}
```

优先级：

```text
运行时 overrides > config.json > 默认值
```

---

## 10. 扩展边界

推荐扩展点：

- 新增模板目录
- 优化索引页模板
- 增强打印 CSS
- 补充测试
- 完善打包发布流程

不推荐扩展点：

- 在 GUI 中复制渲染逻辑
- 在 Python 中硬写浏览器交互
- 为每个模板复制一套 `viewer.js`
- 引入前端框架
