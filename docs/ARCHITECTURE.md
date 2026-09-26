# 架构

## 分层与数据流

```text
core/           Python 调度：配置、转换计划、front matter、目录、渲染调度、索引生成、阅读器资产定位
gui/            pywebview 桌面界面与静态资源
renderer/       Node 渲染服务（v2 production adapter；产物 renderer/dist 随包发布）
node_renderer/  Node 渲染服务（v1 回退：markdown-it 与插件、KaTeX）
viewer/         阅读器外壳、布局与打印样式、交互模块（装配期合并成一个 classic script）
themes/builtin/ 内置主题：base（token 回落）+ modern / office / vscode（可选）
templates/      批量索引页（独立表面，不属于阅读器资产层）
packaging/      打包配置、图标与发布脚本
```

```text
Markdown 文件
  → core/conversion_plan.py   只读预检：递归收集、去重、输出路径、冲突检查
  → core/fm.py                front matter 解析（页面标题）
  → core/renderer_node.py     子进程调用 Node，得到正文 HTML 与标题列表
  → core/toc.py               由标题列表生成嵌套目录
  → core/viewer_assets.py     阅读器资产：外壳、viewer 脚本、打印样式、主题样式链、主题注册表
  → 装配                      正文 + 目录 + 资产 → 单文件 HTML（v2 在 core/html_assembly.py，v1 回退在 core/converter.py）
  → 浏览器                    负责全部阅读交互
```

## 各层职责

### Python（core、gui）

- 只负责调度与组装：不做 Markdown 解析，不实现阅读器交互。
- `conversion_plan.py` 在任何写入之前给出可预览、可校验的转换计划，冲突在写入前拦下。
- `renderer_node.py` 每进程只解析一次 Node 命令；frozen 包只使用内置 Node，缺失即视为打包物损坏。
- `gui/api.py` 把桥接方法暴露给界面；原生对话框一次只开一个，重叠请求被拒绝。

### Node（node_renderer）

- 从标准输入读 JSON，向标准输出写 JSON：正文 HTML、标题列表、警告，以及需要内联的 KaTeX 样式。
- 负责 Markdown 解析、脚注、公式排版与本地图片内嵌，不生成完整阅读器页面。
- 选项与插件范围见 [兼容范围](MARKDOWN.md)。

### 模板（templates）与阅读器资产层

- `core/viewer_assets.py`（Phase 6A）是"阅读器由哪些文件组成、它们在哪"的唯一来源：外壳、viewer 脚本、
  打印样式、主题样式链、主题注册表。两条装配路径与 GUI 都只经它取资产，因此 Phase 6B 搬迁目录时只改这一处。
- **主题 bundle（Phase 6C）**：每份文档固定携带 base + modern + office + vscode（`builtin_theme_css_text()`）。
  主题是独立于明暗的第二维：`html[data-theme-id]` 选 token、`body.theme-<id>` 选组件规则，`viewer/js/theme-switcher.js`
  在阅读器里即时切换（只改标记与一个 localStorage 键，不重新渲染正文）。初始主题写在标记里、菜单由装配期生成，
  因此不存在"无主题"首屏；已保存的阅读器偏好由 boot 恢复（可能与文档默认主题不同，此时有一次可见切换）。
- `default`→`base` 只提供 token；三个可选主题**必须**把自己的 token、组件规则与打印规则 scoped 到
  `html[data-theme-id="<id>"]`，否则会污染其他主题（Office 曾经如此）。
- `viewer.js` 承载全部阅读交互：目录跳转与定位、折叠、状态持久化、代码复制、图片灯箱、明暗、编号与打印。
  拆分（Phase 6B）只能在**装配期**合并成一个 classic script：交付物以 `file://` 打开，ES module 会被 CORS 拦下。
- `print.css` 负责共用打印机械项（隐藏交互控件、分页与缩放规则），纸面观感由各主题自己的打印规则决定。
- `templates/index/` 是独立的索引页模板，读取三份资源后内嵌成单文件 HTML；它不属于阅读器资产层。
- KEEP 表面（DOM id、localStorage 键、class、两个独立状态）见 [Viewer 契约](VIEWER_CONTRACT.md)。

### 打包（packaging）

- 同一 spec 支持 onefile 与 onedir；构建前做真实渲染器自检，产物由 `validate_release.py` 校验。
- `release_freeze.py` 是发布门禁：先核对版本与验收证据，再重建产物、写校验和与构建记录、打并推送 tag。

## 测试分层

- Python 单元与集成测试覆盖转换计划、链接重写、图片内嵌、front matter、模板样式与打包脚本。
- `tests/js/` 是 jsdom 层：驱动真实生成的 viewer、GUI 与索引页，各自锁定契约条数与通过数。
- harness 自检针对测试工具本身；文档契约校验 `samples/demo.html` 与当前源码一致。
- 缺少 Node 或 jsdom 时相应层显式 skip 并说明原因，不会静默通过。

阅读器状态机为什么用行为契约而不是静态断言：折叠状态、阅读位置这类行为只有在真实页面上才能区分
「保留了」与「悄悄丢了」，匹配源码文本做不到。运行方式见 [开发与构建](DEVELOPMENT.md)。
