# Viewer 契约（KEEP 表面）

生成后的 HTML 是产品本体，而且会被离线保存、分发、长期打开。因此"阅读器长什么样、用什么名字存状态"不是实现细节，而是契约。

本文件是 Phase 6（Viewer / Theme 重构）的 KEEP 清单。执行者有三个层次，任何一条消失都必须让它们变红，而不是等到用户浏览器里才发现：

```text
tests/test_viewer_keep_contract.py     名称层：DOM id / 存储键 / class / 属性（本文件第 3–5 节）
tests/test_viewer_state_contract.py    行为层：真实生成 HTML 在 jsdom 里跑 22 条状态契约（条数硬锁）
tests/browser/*.test.mjs               真实浏览器：离线资源、Mermaid、装配产物 smoke
```

## 1. 运行期形态（不可协商）

- 交付物是**单个 standalone HTML**，以 `file://` 打开，离线可用。
- 因此 viewer 只能以**一个 classic script** 内联：`<script type="module">` 在 `file://` 下会被 CORS 拦下，运行期 fetch 模块文件同样破坏离线承诺。
- 源码层可以拆成多个模块（Phase 6B），但必须在**装配期**按声明顺序合并成一个脚本；`core/viewer_assets.py` 提供拼接入口，装配账本仍只有一条 `viewer-js`。

## 2. 两个互相独立的状态

```text
明暗（color scheme）  html[data-theme="dark"]（缺省即 light）    键：markdownreader-theme
主题（theme）          html[data-theme-id="<id>"] + body.theme-<id>   键：markdownreader-theme-id
```

- 二者正交：`Office + dark`、`Modern + light` 都必须成立（6 个组合都在浏览器矩阵里实测）。
- **主题由两个标记共同表达**：`html[data-theme-id]` 选中该主题的 token，`body.theme-<id>` 选中它的组件规则。CSS 两处都要求，因此即使将来一边没更新，也不会两套主题同时命中。
- 不要复用 `data-theme` 表示主题名：它已经被 viewer、print.css、layout.css、三个主题 CSS 与 GUI 共同当作明暗使用。
- 主题状态属于**阅读器偏好**（全局）；文档相关状态一律带文档身份（见第 5 节）。文档自己的**默认主题**是作者在转换时选的那个（`config.json` 的 `template`），它以标记形式写进 HTML：

```text
生成 HTML 在 JS 执行前就带有有效的文档默认主题（html[data-theme-id] + body class）
  → 不存在"无主题"首屏（unthemed flash 不可能发生）

若 localStorage 里存有另一个有效主题
  → viewer boot 时恢复该阅读器偏好（此时会有一次"文档默认 → 已保存主题"的可见切换）
```

- 因此契约是"**永不出现无主题首屏**"，**不是**"持久化主题也永不闪烁"。后一种保证需要在 `<head>` 里放超早期 localStorage bootstrap，会与第 1 节"viewer 只有一个 classic script、模块只在装配期合并"的形态冲突；当前阶段明确不做（若将来要做，需重开 contract）。

## 3. 主题 bundle（每份文档都携带全部 builtin 主题）

```text
每份生成 HTML 里：base 一份 + modern 一份 + office 一份 + vscode 一份
注入顺序固定   ：base → modern → office → vscode（账本 label 为 theme:<id>）
初始状态       ：html[data-theme-id]=<文档默认主题>，body class=theme-<默认主题>
切换           ：只改这两个标记（+ 写 markdownreader-theme-id），不重新渲染正文
```

- base 主题保留**全局** `:root` 与 `[data-theme="dark"]`：它是任何主题没有定义的 token 的回落。
- 三个可选主题的 token、组件规则与打印规则**必须全部 scoped** 到 `html[data-theme-id="<id>"]`（含 `body.theme-<id>` 条件）。Office 曾是唯一没有 scoped 组件规则的主题（85 处 `body …`），6C 已全部收紧。
- 打印：`print.css` 用 `html[data-theme-id][data-theme="dark"]` 把暗色 token 压回白色，与主题的暗色块**同特异性**；print.css 在 bundle 之后注入，因此同分时后者胜出。这条只能靠真实浏览器逐组合验证（`tests/browser/theme_matrix.test.mjs`）。
- 切换时只移除**已知的** `theme-*` class 再添加新的，绝不整体覆盖 `body.className`：将来 body 上若有别的产品 class，必须能熬过一次主题切换。
- 恢复顺序：HTML 先带**文档默认主题**，boot 后若 `markdownreader-theme-id` 是本页有效的主题 id 才切过去。所以"持久化主题 ≠ 文档默认主题"时会有一次可见切换（见第 2 节的两行契约）。
- builtin 主题是随包必需资产：任一可选主题的 `theme.css` 缺失时装配**硬失败**，不产出缺主题变量的 HTML（6B 及以前只降级）。

## 4. DOM id（15 个）

`viewer.html` 提供的钩子，viewer JS 与索引页/测试都按名字取用：

| id | 用途 |
| --- | --- |
| `toolbar` | 工具条容器 |
| `btn-expand-all-content` / `btn-collapse-all-content` | 正文层级展开 / 折叠 |
| `btn-auto-numbering` | 自动编号开关（转换期也会点它） |
| `btn-theme` | 主题选择器按钮（`aria-expanded` 反映菜单状态） |
| `theme-menu` | 主题菜单容器（`hidden` 属性即收起） |
| `btn-dark-mode` | 明暗切换 |
| `btn-print` | 打印 |
| `toc-sidebar` | 目录侧栏 |
| `btn-toggle-toc-panel` | 侧栏折叠 |
| `toc-body` | 目录主体（ScrollSpy / fold 在此工作） |
| `toc-resizer` | 目录宽度拖拽 |
| `content-area` | 滚动容器（阅读位置、IntersectionObserver 的 root） |
| `markdown-body` | 正文容器（折叠、灯箱、代码复制、表格滚动） |
| `back-to-top-btn` | 返回顶部 |

菜单项不打 id，用属性选择器契约：`#theme-menu [data-theme-id]`，文本是**可读名称**（`metadata.json` 的 `name`，如 `Modern` / `Office` / `VS Code`），不是 canonical id。菜单标记由装配期生成（不是 JS 拼的），因此页面在没有脚本时也是正确的。

## 5. localStorage 键（9 个）

| 键 | 作用域 | 说明 |
| --- | --- | --- |
| `markdownreader-doc-state-v2:<pathname>` | 每文档 | 折叠基线 + 用户 override |
| `markdownreader-scroll-<pathname>` | 每文档 | 阅读位置（`<pathname>` 即 `location.pathname`） |
| `markdownreader-toc-collapsed-v2` | 阅读器 | 目录折叠集合 |
| `markdownreader-toc-panel-collapsed` | 阅读器 | 侧栏是否收起 |
| `markdownreader-theme` | 阅读器 | 明暗（`light` / `dark`） |
| `markdownreader-theme-id` | 阅读器 | 主题 id；值不在本页携带的主题里时回落到**文档默认主题** |
| `markdownreader-autonumbering` | 阅读器 | 自动编号开关 |
| `markdownreader-toc-width` | 阅读器 | 目录宽度（180–500px） |
| `markdownreader-expandlevel` | 阅读器 | **只读遗留**：仅在文档没有 v2 状态时作种子，永不写入 |

GUI 自己的 `gui-theme` 属于应用外壳，不属于生成文档。

## 6. class / 属性 / CSS 变量

- TOC：`.toc-row[data-id][data-level]`、`.toc-toggle`、`.toc-link`、`.active`
- 折叠：`.is-collapsed`（TOC 分支）、`.is-hidden-by-collapse`、`.is-hidden-by-content-fold`、`.heading-toggle`
- 组件：`.code-block-wrapper`、`.copy-btn`、`.table-wrapper`、`.viewer-container`
- 主题：`.theme-picker`、`.theme-menu`（`[hidden]` 即收起）、`.theme-menu .theme-option`、`.theme-option.active`
- 拖拽：`.resizing`（body 上临时加）
- 明暗 / 编号 / 主题：`html[data-theme]`、`html[data-auto-numbering]`、`html[data-theme-id]`
- 布局变量：`--sidebar-width`（拖拽写入 `<html>` 的内联样式）

## 7. 明确**不是**契约（可以自由改）

- viewer JS 的内部函数名、模块边界、文件切分方式；
- CSS 文件的切分与命名（`viewer.css` / `theme.css` 是否合并、拆分）；
- 主题变量的具体取值、字体名、装饰细节；
- **仓库内**资产目录的位置（`viewer/`、`themes/builtin/` 的布局、文件切分、主题 CSS 的文件名）；
- 生成 HTML 里样式块的**排列方式**（但注入顺序 viewer → theme → 资源 → print 必须保持，见 `core/html_assembly.py` 的确定性顺序）；
- `body.theme-<id>` 的**id 取值**可以扩展（新主题），但既有三个 id 不可改名 —— 改名等于让老 HTML 的 localStorage 选择失效；
- 主题菜单的视觉（位置、size、hover 样式）与工具条按钮的图标；
- 主题菜单里名称的**文案**（`metadata.json` 的 `name` 可改），但"菜单项必须带 `data-theme-id`"是契约。

## 8. 资产知识只有一处来源

Phase 6A 起，viewer/theme 资产的定位与读取集中在 `core/viewer_assets.py`：

```text
theme_ids()               可选的 builtin 主题（有 metadata.json 且非 hidden）
builtin_themes()          [(id, 可读名称)]，名称来自 metadata.json，供菜单使用
theme_metadata(id)        metadata.json
theme_body_class(id)      body class（theme-<id>）
theme_css_text(id)        单个主题的 theme.css（bundle 用；缺失即失败）
builtin_theme_css_text()  base + 每个可选主题，各一次，顺序固定（交付文档的主题载荷）
theme_css_chain(id)       单主题样式链（诊断/外置主题用，不再是 production 载荷来源）
theme_menu_markup()       主题菜单标记（shell 的 {{THEME_MENU}}）
validate_theme(id)        主题可用性校验（存在 / 继承可解 / 可选），装配路径第一步
viewer_shell_text()       页面外壳
viewer_layout_css_text()  布局/组件样式（只消费变量）
shared_viewer_js_text()   viewer 脚本（按 manifest 拼接）
shared_print_css_text()   打印样式
```

`core/config.py` 只管 config.json 与 bundle 路径，不反向依赖该模块；`core/converter.py`（v1 回退路径）与 `core/html_assembly.py`（v2）都只经它取资产；`gui/api.py` 的主题列表也来自它。

Phase 6B 起 `templates/` 只剩批索引页；阅读器资产在 `viewer/`（外壳、样式、脚本）与 `themes/builtin/<id>/`（主题）。两个装配路径与 GUI 都只经本模块取资产，因此搬迁只改了这一个文件。

viewer 脚本是**按 `viewer/js/manifest.json` 顺序、空分隔拼接**的同一个 IIFE 片段：拼接结果必须与拆分前的单文件逐字节相同（由 `samples/demo.html` 比对与 `tests/test_viewer_assets_contract.py` 共同保证）。模块文件必须以换行结尾，否则加载器直接报错 —— 粘连比失败更难查。原文件开头有一个 UTF-8 BOM 且它进入了交付文档，所以由加载器显式补回（`_VIEWER_JS_BOM`），源模块不含 BOM。

Phase 6B 之后"v1 回退"仅表示 renderer 语义回退，不表示回退整套 Viewer 文件（视觉层只有一套）。

Phase 6D 只做文档收口：本清单里的名字、键与钩子一个都没有变，`samples/demo.html` 逐字节不变。

## 9. 外置主题（Phase 7）

```text
安装位置   assets/themes/external/<id>/（用户资产，永不随包）
加载协议   与 builtin 同一个 loader：metadata.json 的 id / name / extends / files
文档载荷   base + 全部 builtin + 本次选中且已安装的外置（账本 theme:<id>）
菜单       装配期生成；阅读器零 JS 改动即可切换（第 3、6 节依旧成立）
```

- 外置主题**只做视觉**：禁止 JS、禁止自定义 Viewer DOM、禁止 `@import` 与远程 `url()`；本地资源在装配期内嵌成 data URI，
  因此**删掉主题后已生成的 HTML 仍可用**（Phase 7 验收第 3 条，`tests/browser/external_theme.test.mjs` 实测）。
- 保留 ID：`base` / `modern` / `office` / `vscode`（以及历史名 `default`）不得作为外置主题 id；
  id 形如 `^[a-z][a-z0-9-]{1,31}$`，安装目录名即 id。
- 主题必须把所有规则 scoped 到 `html[data-theme-id="<自己的 id>"]`（第 3 节），组件规则再加 `body.theme-<id>`。
- `config.json` 的 `external_themes` 只写 id（不写路径）；不存在或已删除的 id 忽略并记 warning，不阻断转换（第 5 节）。
- **extends 只能是 `base` 或 null**（Phase 7 audit follow-up 收紧）。selectable builtin（modern/office/vscode）在 6C 之后把
  规则 scoped 到各自 id，external 继承它们是语义假的；真要"基于 Office 做 Paper"需要另行设计 selector rebasing / token
  inheritance，而不是 metadata 写个 `extends`。
- **每次读取都重新校验**（audit follow-up）：主题 CSS 会被原样放进 `<style>`，而安装目录是持久用户资产（将来还有编辑入口），
  所以 `import_theme()` 的校验不是永久凭证 —— `inline_theme_css()` 与 selection 解析都会先跑 `validate_installed_theme()`：
  目录名 == metadata id、声明文件与资源不逃逸（realpath containment）、体积与内嵌载荷在预算内、CSS 通过策略检查。
  损坏的**已安装**主题是硬失败；只是**未安装**（ghost id）才忽略 + warning。
- **CSS 策略由 `core/css_audit.py` 的一个 fail-closed 扫描器执行**：每条规则必须 scoped 到 canonical 的
  `html[data-theme-id="<id>"]`（`@media`/`@supports` 递归；其余 at-rule 一律拒绝 —— `@keyframes`/`@font-face` 拥有全局命名、
  `@page` 无法 scope、`@charset`/`@layer`/`@namespace` 对"按 UTF-8 读取并拼接"的文件没有意义）；`url()` 目标禁止 CSS 转义
  （因此 `https\3a //…` 无法伪装 scheme）；data URI 走 MIME 白名单（SVG 暂不放行）；注释/字符串未闭合、括号不平衡等
  无法证明安全的写法直接拒绝。closure checker 共用这个**扫描器**，但保留自己"什么算 inline"的策略。
- **体积按最终载荷计算**：声明 CSS 的 UTF-8 字节 + 每一次实际 `data:` 展开的 base64 字节与前缀（重复引用计两次），
  不是目录大小。
- **warning 走正式通道**：selection 解析产生的 warning 进入装配返回的 `assembly_warnings`，v2 合并进 conversion report，
  v1 追加进自己的 report —— 不再只有日志。
