# 架构

## 分层与数据流

```text
core/           Python 调度：配置、转换计划、front matter、目录、渲染调度、索引生成、阅读器资产定位
gui/            pywebview 桌面界面；api.py 是稳定 façade，services/ 按对话框、转换、主题和生命周期/存储分工
                assets/js/ 的 GUI 脚本按职责拆分，由 manifest 按序组装成内联 classic script
renderer/       Node 渲染服务（v2 production adapter；产物 renderer/dist 随包发布）
viewer/         阅读器外壳、布局与打印样式、交互模块（装配期合并成一个 classic script）
themes/builtin/ 内置主题：base（token 回落）+ modern / office / vscode（可选）
templates/      批量索引页（独立表面，不属于阅读器资产层）
packaging/      打包配置、图标与发布脚本
```

```text
Markdown 文件
  → core/conversion_plan.py   只读预检：递归收集、去重、输出路径、冲突检查
  → core/fm.py                front matter 解析（页面标题）
  → core/renderer_node.py     校验 Node 运行时并调用 v2 renderer，取得完整 envelope
  → core/toc.py               由标题列表生成嵌套目录
  → core/viewer_assets.py     阅读器资产：外壳、viewer 脚本、打印样式、主题样式链、主题注册表
  → core/html_assembly.py      正文 + 目录 + 资源 → 单文件 HTML
  → 浏览器                    负责全部阅读交互
```

## 各层职责

### Python（core、gui）

- 只负责调度与组装：不做 Markdown 解析，不实现阅读器交互。
- `conversion_plan.py` 在任何写入之前给出可预览、可校验的转换计划，冲突在写入前拦下。
- `renderer_node.py` 每进程只解析一次 Node 命令；frozen 包只使用内置 Node，缺失即视为打包物损坏。
- `gui/api.py` 是稳定的 pywebview façade，保留 `pywebview.api.*` 方法与数据契约；内部由 `gui/services/` 的
  对话框/输入、转换、主题、生命周期/存储服务承接工作。
- 生命周期服务统一管理终止移除状态与在途操作 gate；对话框服务独立串行化 Tk 对话框。服务拆分不改变 GUI bridge
  方法、参数或返回 shape。
- GUI 前端脚本位于 `gui/assets/js/`，由 `manifest.json` 固定装载顺序。`gui/app.py` 将片段组装为一个内联 classic
  script，避免运行时请求本地模块；该结构只调整源码组织，不改变 DOM、bridge API 或初始化顺序。

### Node 渲染器

- `renderer/` 是唯一支持的 renderer，复用 pinned `vscode-office` 语义并返回完整 envelope；
  `core/html_assembly.py` 将 envelope 装配为最终单文件 HTML。
- `core/renderer_node.py` 在启动期检查 Node 版本与 v2 artifact。首次真实渲染把离线 KaTeX/runtime smoke
  与文档渲染放在同一个 Node 进程中；Python 校验 smoke envelope 后只向 assembly 交付正式文档 envelope。
  后续 one-shot 请求仍各自启动 renderer，长连接复用由 G2 引入。
- renderer 或 artifact 失败时明确报错；首次 smoke 失败不会缓存运行时验证结果。
- `core/config.py::PRODUCTION_RENDERER_VERSION` 是 GUI 与 QA 使用的 renderer 版本标识，不提供运行时选择器。
- 选项与语法范围见 [兼容范围](MARKDOWN.md)；迁移状态与测试证据见 [兼容矩阵](MARKDOWN_COMPATIBILITY.md)。

### 模板（templates）与阅读器资产层

- `core/viewer_assets.py`（Phase 6A）是"阅读器由哪些文件组成、它们在哪"的唯一来源：外壳、viewer 脚本、
  打印样式、主题样式链、主题注册表。两条装配路径与 GUI 都只经它取资产，因此 Phase 6B 搬迁目录时只改这一处。
- **主题 bundle（Phase 6C）**：每份文档固定携带 base + modern + office + vscode（`builtin_theme_css_text()`）。
  主题是独立于明暗的第二维：`html[data-theme-id]` 选 token、`body.theme-<id>` 选组件规则，`viewer/js/theme-switcher.js`
  在阅读器里即时切换（只改标记与一个 localStorage 键，不重新渲染正文）。初始主题写在标记里、菜单由装配期生成，
  因此不存在"无主题"首屏；已保存的阅读器偏好由 boot 恢复（可能与文档回落主题不同，此时有一次可见切换）。
  Phase 12 起该回落值来自 GUI 边界常量 `BOOTSTRAP_TEMPLATE`（GUI 不再有内置主题选择器），阅读端语义不变。
- `default`→`base` 只提供 token；三个可选主题**必须**把自己的 token、组件规则与打印规则 scoped 到
  `html[data-theme-id="<id>"]`，否则会污染其他主题（Office 曾经如此）。
- **外置主题（Phase 7）**：用户主题是用户资产，装在 `core/paths.py::external_themes_root()`
  （`assets/themes/external/<id>/`），与随包的 `themes/builtin/` 永不混放；同一个 loader 读两者，
  `external_themes.theme_bundle()` 决定每份文档携带哪些（base + 全部 builtin + 本次选中且已安装的外置）。
  校验 / 安装 / 删除 / 导出模板在 `core/external_themes.py`（含可选的 `preview` 元数据与本地装饰资源）；
  `replace=True` 先在同卷事务目录复制并复验，再备份旧目录、发布新目录，发布失败时恢复旧版本。
  `themes/template/` 是随包发布的官方模板。
- `viewer.js` 承载全部阅读交互：目录跳转与定位、折叠、状态持久化、代码复制、图片灯箱、明暗、编号与打印。
  拆分（Phase 6B）只能在**装配期**合并成一个 classic script：交付物以 `file://` 打开，ES module 会被 CORS 拦下。
- `print.css` 负责共用打印机械项（隐藏交互控件、分页与缩放规则），纸面观感由各主题自己的打印规则决定。
- `templates/index/` 是独立的索引页模板，读取三份资源后内嵌成单文件 HTML；它不属于阅读器资产层。
- KEEP 表面（DOM id、localStorage 键、class、两个独立状态）见 [Viewer 契约](VIEWER_CONTRACT.md)。

### 打包（packaging）

- 同一 spec 支持 onefile 与 onedir；构建前做真实渲染器自检，产物由 `validate_release.py` 校验。
- `release_freeze.py` 是发布门禁：tag 发布前核对版本、验收身份与精确产物哈希，复用实机验收过的候选文件，写校验和与构建记录并推送 tag。

## 测试分层

- Python 单元与集成测试覆盖转换计划、链接重写、图片内嵌、front matter、模板样式与打包脚本。
- `tests/js/` 是 jsdom 层：驱动真实生成的 viewer、GUI 与索引页，各自锁定契约条数与通过数。
- harness 自检针对测试工具本身；文档契约校验 `samples/demo.html` 与当前源码一致。
- 缺少 Node 或 jsdom 时相应层显式 skip 并说明原因，不会静默通过。

阅读器状态机为什么用行为契约而不是静态断言：折叠状态、阅读位置这类行为只有在真实页面上才能区分
「保留了」与「悄悄丢了」，匹配源码文本做不到。运行方式见 [开发与构建](DEVELOPMENT.md)。
