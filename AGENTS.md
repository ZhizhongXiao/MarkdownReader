# MarkdownReader AI Engineering Rules

本文件是 MarkdownReader 项目的长期工程约束。

任何 AI 编码代理在修改本项目之前，都必须先阅读本文件，以及与当前任务相关的 `docs/` 文档。

---

# 1. 项目定位

MarkdownReader 是一个将 Markdown 文件转换为可离线阅读、可交互、尽可能单文件保存的静态 HTML 文档生成器。

典型工作流：

```text
VS Code / vscode-office
        ↓
编辑并保存 Markdown
        ↓
MarkdownReader
        ↓
静态 HTML
        ↓
浏览器阅读 / 打印 / 分发
```

MarkdownReader：

- 不是 Markdown 编辑器；
- 不负责 WYSIWYG；
- 不负责实时预览；
- 不编辑 Markdown 源文件；
- 不提供云同步、多人协作或 Web 服务。

生成的 HTML 是核心产品。

---

# 2. 总体架构原则

MarkdownReader 后续采用以下职责边界：

```text
vscode-office
    ↓
Markdown 语义解析与主要语法扩展

MarkdownReader renderer adapter
    ↓
兼容层、必要附加语法、资源处理

MarkdownReader core
    ↓
转换计划、文件关系、TOC、文档装配

Viewer
    ↓
阅读、交互、状态保存

Themes
    ↓
纯视觉表现

GUI
    ↓
转换入口和设置
```

不得重新把这些职责混合到单个“大文件”中。

---

# 3. vscode-office 是 Markdown 语义的主要上游

本项目不再自行重复实现 vscode-office 已经实现的 Markdown 语法。

目标是让 vscode-office 成为主要 Markdown 语义来源，包括但不限于：

- task checkbox；
- mark；
- Callout；
- WikiLink；
- Obsidian tag；
- KaTeX；
- Mermaid；
- PlantUML；
- anchor；
- 未来 vscode-office 新增且适用于导出 HTML 的 Markdown 扩展。

但不得为了“上游化”删除 MarkdownReader 已经具有、而 vscode-office 当前没有的必要能力。

例如：

- footnote；
- Markdown 文档链接 `.md → .html` 重写；
- MarkdownReader 特有数学兼容；
- 本地资源内嵌；
- 远程资源获取；
- heading metadata；
- warnings；
- standalone HTML 资源封装。

原则：

> 上游负责“Markdown 表达什么意思”；MarkdownReader 负责“怎样把结果交付成阅读文档”。

---

# 4. 上游源码规则

`upstream/vscode-office/` 视为第三方上游代码。

规则：

1. 不直接修改上游源码。
2. 不复制若干上游文件后形成无人维护的 fork。
3. 所有兼容处理放在 MarkdownReader adapter。
4. 上游更新必须是显式操作。
5. 每次更新上游后必须运行完整兼容测试。
6. MarkdownReader 必须记录当前已经验证的 vscode-office commit。
7. 不允许未经测试直接追随 upstream `main`。

优先使用 Git submodule。

如采用 sparse-checkout，必须通过项目脚本可重复建立；如果 sparse-checkout 使初始化明显变脆弱，应优先保留完整 submodule，而不是为了节省少量磁盘空间增加维护成本。

---

# 5. Renderer 规则

Renderer 应拆为多个小职责模块。

目标概念结构：

```text
renderer/
├─ entry.js
├─ protocol.js
├─ upstream/
├─ extensions/
├─ document/
├─ assets/
└─ components/
```

禁止重新形成一个数百行同时负责：

- markdown-it 初始化；
- 插件；
- heading；
- link；
- image；
- resource；
- network；
- asset；
- protocol；

的单一 `render.js`。

一个文件应尽量只承担一种职责。

不要为了“小文件”机械拆分没有独立语义的三五行代码；以职责边界为准。

---

# 6. Front Matter

MarkdownReader 当前使用 Front Matter 获取文档 metadata，例如页面 title。

不要直接启用 vscode-office 将 YAML Front Matter 渲染成正文 Properties 面板的行为，除非未来有明确需求。

默认行为：

```text
Front Matter
→ metadata
→ 不进入正文
```

---

# 7. Heading / TOC

Heading anchor 应尽可能与 vscode-office 的 Markdown 导出行为一致。

MarkdownReader：

- 可以读取 heading ID；
- 可以生成自己的 TOC；
- 可以保存 TOC 特有 metadata；
- 不应再维护一套没有必要的独立 heading slug 定义。

现有 TOC 的：

- 编号识别；
- 折叠；
- ScrollSpy；
- 自动编号；
- 阅读状态；

属于 MarkdownReader，不属于 vscode-office。

---

# 8. 单文件交付

最终 HTML 应尽可能自包含。

本地资源：

```text
本地图片
CSS资源
KaTeX字体
主题资源
```

应尽可能转换为 data URI 或直接内嵌。

远程资源默认策略：

```text
联网
→ 尝试获取并内嵌

失败 / 无网
→ 保留原 URL
→ 输出 warning
→ 转换继续
```

网络资源获取失败不得默认导致整个 Markdown 转换失败。

README 应明确：

> 推荐联网转换，以获得最完整的 standalone HTML；无网络时 MarkdownReader 仍可转换，并保留无法获取资源的原始 URL。

---

# 9. Mermaid

Mermaid 浏览器 runtime 必须按需加入。

没有 Mermaid 的文档：

```text
不得内嵌 Mermaid runtime
```

出现 Mermaid：

```text
才加入 Mermaid 所需 JS/CSS
```

不要为了可能使用的功能永久扩大所有 HTML 文件。

---

# 10. PlantUML

当前阶段只支持网络 PlantUML Server。

不得加入：

- bundled Java；
- PlantUML JAR；
- Docker；
- 本地 PlantUML Server；
- 后台服务。

PlantUML 图形生成后：

```text
联网成功
→ 获取图像
→ 尽可能内嵌进 HTML

失败
→ 保留远程 URL
→ warning
→ 转换继续
```

应把 PlantUML server URL 抽象为配置，而不是散落硬编码。

---

# 11. Theme，而不是 Template

用户可切换的视觉系统统一称为 Theme / 主题。

Viewer 与 Theme 是两个独立概念。

```text
Viewer
→ DOM、交互、布局机制

Theme
→ 视觉
```

不得把 Viewer 再称作主题。

三个内置主题：

- Modern
- Office
- VS Code

永远进入每一个生成 HTML。

GUI 不再要求用户在三者中预先选择一个。

HTML 阅读时由用户自行切换。

---

# 12. Theme 与明暗模式是两个状态

Theme：

```text
modern
office
vscode
external theme
```

Color scheme：

```text
light
dark
```

二者必须独立。

允许：

```text
Office + light
Office + dark
Modern + light
Modern + dark
```

不得把二者共用同一个配置概念。

---

# 13. Semantic component CSS

vscode-office 特有语义组件应具有 MarkdownReader 的默认兼容样式，例如：

```text
checkbox
callout
mark
wikilink
obsidian-tag
mermaid
plantuml
```

推荐结构：

```text
renderer/components/
```

组件层提供合理默认值。

主题可以覆盖其 CSS variables 或 selectors。

主题没有定义某个组件时：

> 使用组件默认样式。

不得强迫每一个主题完整复制所有组件 CSS。

也不得直接把整个 vscode-office `markdown-pdf.css` 注入 MarkdownReader，因为普通：

- `pre`
- `blockquote`
- `code`
- heading
- table

等基础排版应由 MarkdownReader Theme 控制。

---

# 14. 外置主题

外置主题只负责视觉。

第一版禁止：

- 自定义 Viewer DOM；
- 自定义 viewer.html；
- 自定义 JavaScript；
- 任意执行代码。

推荐主题目录：

```text
theme-id/
├─ metadata.json
├─ variables.css
├─ content.css
├─ components.css
├─ print.css
└─ assets/
```

主题 metadata 应声明实际 CSS 文件列表。

CSS 中本地 `url(...)` 资源在生成 HTML 时应尝试内嵌。

外置主题不得覆盖保留 ID：

```text
default
modern
office
vscode
```

---

# 15. 内置主题

三个 builtin theme 必须与 external theme 使用同一个 Theme Loader 协议。

禁止：

```text
builtin 使用特殊加载逻辑
external 使用另一套逻辑
```

区别只能是来源和是否强制包含。

---

# 16. Theme template

程序必须内置一份正式的外置主题开发模板：

```text
themes/template/
```

至少包括：

```text
metadata.json
variables.css
content.css
components.css
print.css
README.md
assets/
```

GUI 设置页必须提供：

```text
导出主题模板
```

用户可以选择目标目录，将完整模板复制出去进行修改。

---

# 17. 外置主题生命周期

主题管理：

```text
设置页
→ 导入
→ 删除
→ 导出主题模板
→ 打开主题目录
```

本次生成 HTML 时包含哪些已安装外置主题：

```text
主页面
```

二者不得混淆。

主页面应记忆上次选择。

`config.json` 只保存 theme ID，例如：

```json
{
  "external_themes": [
    "paper",
    "academic"
  ]
}
```

禁止保存绝对路径。

已配置但已经不存在的 theme：

```text
忽略
→ warning / log
→ 不阻止转换
```

---

# 18. HTML 内主题状态

MarkdownReader `config.json` 保存：

> 下一次生成 HTML 时包含哪些外置主题。

生成后的 HTML 自己的 localStorage 保存：

> 阅读该 HTML 时用户最后选择了哪个主题。

两者不得互相耦合。

---

# 19. Viewer

Viewer 应拆为多个职责清晰的小模块。

现有重要功能必须保留：

- TOC navigation；
- ScrollSpy；
- TOC fold；
- content fold；
- fold state；
- reading position；
- image lightbox；
- code copy；
- table horizontal scroll；
- auto numbering；
- dark/light；
- TOC resize；
- back to top；
- print。

新增：

- theme switcher。

不要为了主题重构破坏现有 Viewer 行为契约。

---

# 20. GUI

GUI 使用 pywebview + HTML/CSS/JavaScript。

当前规模不需要引入 React/Vue 等前端框架。

GUI 分：

```text
主页面
设置页
```

设置页平时隐藏。

设置入口放在 GUI 顶部昼夜模式按钮附近。

主页面负责：

- 输入；
- 输出；
- 转换预检；
- 本次选中的外置主题；
- 转换参数；
- 运行状态。

设置页负责：

- 外置主题安装和管理；
- 导出主题模板；
- 打开外置主题目录；
- 用户偏好/资产位置；
- 关于；
- “移除 MarkdownReader 用户数据并退出”。

不提供：

- 清理缓存按钮；
- 打开日志按钮；
- 泛化的“清理用户数据”。

---

# 21. 用户持久化内容分类

用户偏好与用户资产不得和日志/缓存混为一类。

概念：

```text
profile/
→ 用户偏好

assets/
→ 用户资产

runtime/
→ 可再生运行数据
```

`config.json` 属于 profile。

外置主题属于 assets。

日志等属于 runtime。

---

# 22. onedir 与 onefile

两个发布目标都是正式支持对象。

## onedir

所有内容局限在自己的目录。

例如：

```text
MarkdownReader/
├─ MarkdownReader.exe
├─ _internal/
└─ data/
   ├─ profile/
   ├─ assets/
   └─ runtime/
```

删除整个目录即完整移除。

## onefile

程序：

```text
MarkdownReader.exe
```

持久化用户内容：

```text
%LOCALAPPDATA%\MarkdownReader/
├─ profile/
├─ assets/
└─ runtime/
```

GUI 设置页应显示这个位置并允许打开。

---

# 23. 移除 onefile 用户数据

不实现 EXE 自删除。

设置页提供：

```text
移除 MarkdownReader 用户数据并退出
```

点击后必须出现明确确认对话框。

确认按钮：

```text
最初 disabled
5 秒倒计时
倒计时结束后才允许确认
```

取消按钮始终可用。

确认后：

1. 禁止后续配置/日志写入；
2. 删除 MarkdownReader 用户 profile；
3. 删除用户 assets；
4. 删除 runtime；
5. 尝试移除空根目录；
6. 退出程序。

不得在 shutdown 阶段重新生成 config 或日志。

---

# 24. 路径管理

所有：

- source；
- onedir；
- onefile；
- bundle；
- profile；
- assets；
- runtime；

路径判断集中到一个小型路径模块，例如：

```text
core/paths.py
```

其它业务模块不允许散落判断：

```python
if sys.frozen ...
if _MEIPASS ...
```

业务代码必须调用路径 API。

---

# 25. 测试规则

修改行为前，必须先确认现有测试覆盖。

新增功能必须有对应测试。

至少覆盖：

- Markdown 基础语法；
- checkbox；
- mark；
- Callout；
- WikiLink；
- footnote；
- KaTeX；
- Mermaid；
- PlantUML；
- local image；
- remote image；
- `.md → .html`；
- Front Matter；
- heading anchor；
- TOC；
- 三个 builtin themes；
- external theme；
- HTML theme switching；
- dark/light；
- Viewer state；
- 中文路径；
- 含空格路径；
- 无网络 fallback；
- onedir；
- onefile。

测试不得通过删除已有 assertion 或简单放宽 contract 来“解决”。

行为变化必须明确记录原因。

---

# 26. 迁移纪律

这是渐进迁移，不是重写。

在新 renderer 被测试证明等价或更完整之前：

> 不删除旧 renderer。

推荐顺序：

```text
建立新实现
→ 两套并存
→ 对照测试
→ 新实现达到验收要求
→ 切换默认
→ 再删除旧实现
```

GUI、Viewer、Renderer 不应在同一阶段同时进行大规模重写。

一次只解决一个架构层。

---

# 27. 修改范围纪律

每次任务开始时：

1. 明确当前阶段；
2. 阅读相关源码；
3. 给出准备修改的文件；
4. 解释为什么；
5. 再开始修改。

不得因为“顺便整理”而修改当前任务无关模块。

发现额外技术债：

> 记录，不顺手扩大范围。

---

# 28. 依赖纪律

新增依赖前必须说明：

- 为什么需要；
- 为什么现有依赖不能解决；
- 对源码运行的影响；
- 对 onefile/onedir 的影响；
- 对最终 HTML 大小的影响。

不得全局安装项目依赖。

Node 依赖使用项目自己的 package manifest / lockfile。

Python 依赖写入正式项目依赖定义。

---

# 29. npm 可复现性

MarkdownReader 自己的 renderer 必须维护 lockfile。

不能假定：

```text
同一个 vscode-office commit
=
以后 npm install 一定得到相同依赖
```

上游依赖版本与 MarkdownReader renderer 的验证版本必须可追踪。

---

# 30. Git 安全

未经用户明确要求：

- 不 force push；
- 不 `reset --hard`；
- 不删除 branch/tag；
- 不重写历史；
- 不自动 merge main；
- 不自动创建 release；
- 不自动 push。

可以建议 commit 点，但不要擅自提交或推送。

---

# 31. 完成任务前必须执行

每次完成一个阶段：

1. 运行与当前修改相关的测试；
2. 运行必要的回归测试；
3. 检查 `git diff`；
4. 检查是否意外修改上游；
5. 更新相关文档；
6. 给出：
   - 修改摘要；
   - 测试结果；
   - 已知限制；
   - 下一阶段建议。

“代码能启动”不等于验收通过。

---

# 32. 设计优先级

发生取舍时优先顺序：

```text
正确性
> 可维护性
> 可测试性
> 上游可更新性
> standalone HTML 完整性
> 用户体验
> 性能优化
> 代码数量最少
```

不要为了减少几行代码破坏职责边界。

不要为了所谓“工程化”引入与项目规模不匹配的抽象。

目标是结构清楚，而不是复杂。