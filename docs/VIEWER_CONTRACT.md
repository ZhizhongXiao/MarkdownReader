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
主题（theme）          body.theme-<id>                           键：markdownreader-theme-id（Phase 6C 引入）
```

- 二者正交：`Office + dark`、`Modern + light` 都必须成立。
- 不要复用 `data-theme` 表示主题名：它已经被 `viewer.js`、`print.css`、`viewer.css`、三个主题 CSS 与 GUI 共同当作明暗使用。
- 主题状态属于**阅读器偏好**（全局），与文档无关；文档相关状态一律带文档身份（见第 4 节）。

## 3. DOM id（13 个）

`viewer.html` 提供的钩子，viewer JS 与索引页/测试都按名字取用：

| id | 用途 |
| --- | --- |
| `toolbar` | 工具条容器 |
| `btn-expand-all-content` / `btn-collapse-all-content` | 正文层级展开 / 折叠 |
| `btn-auto-numbering` | 自动编号开关（转换期也会点它） |
| `btn-dark-mode` | 明暗切换 |
| `btn-print` | 打印 |
| `toc-sidebar` | 目录侧栏 |
| `btn-toggle-toc-panel` | 侧栏折叠 |
| `toc-body` | 目录主体（ScrollSpy / fold 在此工作） |
| `toc-resizer` | 目录宽度拖拽 |
| `content-area` | 滚动容器（阅读位置、IntersectionObserver 的 root） |
| `markdown-body` | 正文容器（折叠、灯箱、代码复制、表格滚动） |
| `back-to-top-btn` | 返回顶部 |

## 4. localStorage 键（8 个）

| 键 | 作用域 | 说明 |
| --- | --- | --- |
| `markdownreader-doc-state-v2:<pathname>` | 每文档 | 折叠基线 + 用户 override |
| `markdownreader-scroll-<pathname>` | 每文档 | 阅读位置（`<pathname>` 即 `location.pathname`） |
| `markdownreader-toc-collapsed-v2` | 阅读器 | 目录折叠集合 |
| `markdownreader-toc-panel-collapsed` | 阅读器 | 侧栏是否收起 |
| `markdownreader-theme` | 阅读器 | 明暗（`light` / `dark`） |
| `markdownreader-autonumbering` | 阅读器 | 自动编号开关 |
| `markdownreader-toc-width` | 阅读器 | 目录宽度（180–500px） |
| `markdownreader-expandlevel` | 阅读器 | **只读遗留**：仅在文档没有 v2 状态时作种子，永不写入 |

GUI 自己的 `gui-theme` 属于应用外壳，不属于生成文档。

## 5. class / 属性 / CSS 变量

- TOC：`.toc-row[data-id][data-level]`、`.toc-toggle`、`.toc-link`、`.active`
- 折叠：`.is-collapsed`（TOC 分支）、`.is-hidden-by-collapse`、`.is-hidden-by-content-fold`、`.heading-toggle`
- 组件：`.code-block-wrapper`、`.copy-btn`、`.table-wrapper`、`.viewer-container`
- 拖拽：`.resizing`（body 上临时加）
- 明暗与编号：`html[data-theme]`、`html[data-auto-numbering]`
- 布局变量：`--sidebar-width`（拖拽写入 `<html>` 的内联样式）

## 6. 明确**不是**契约（可以自由改）

- viewer JS 的内部函数名、模块边界、文件切分方式；
- CSS 文件的切分与命名（`viewer.css` / `theme.css` 是否合并、拆分）；
- 主题变量的具体取值、字体名、装饰细节；
- **仓库内**资产目录的位置（`viewer/`、`themes/builtin/` 的布局、文件切分、主题 CSS 的文件名）；
- 生成 HTML 里样式块的**排列方式**（但注入顺序 viewer → theme → 资源 → print 必须保持，见 `core/html_assembly.py` 的确定性顺序）；
- `body.theme-<id>` 的**id 取值**可以扩展（新主题），但既有三个 id 不可改名 —— 改名等于让老 HTML 的 localStorage 选择失效。

## 7. 资产知识只有一处来源

Phase 6A 起，viewer/theme 资产的定位与读取集中在 `core/viewer_assets.py`：

```text
theme_ids()               注册表（有 metadata.json 且非 hidden）
theme_metadata(id)        metadata.json
theme_body_class(id)      body class（theme-<id>）
theme_css_chain(id)       样式链（base → child）
viewer_shell_text(id)     页面外壳
viewer_layout_css_text()  布局/组件样式（只消费变量）
shared_viewer_js_text()   viewer 脚本（Phase 6B 在此按 manifest 拼接）
shared_print_css_text()   打印样式
```

`core/config.py` 只管 config.json 与 bundle 路径，不反向依赖该模块；`core/converter.py`（v1 回退路径）与 `core/html_assembly.py`（v2）都只经它取资产；`gui/api.py` 的主题列表也来自它。

Phase 6B 起 `templates/` 只剩批索引页；阅读器资产在 `viewer/`（外壳、样式、脚本）与 `themes/builtin/<id>/`（主题）。两个装配路径与 GUI 都只经本模块取资产，因此搬迁只改了这一个文件。

viewer 脚本是**按 `viewer/js/manifest.json` 顺序、空分隔拼接**的同一个 IIFE 片段：拼接结果必须与拆分前的单文件逐字节相同（由 `samples/demo.html` 比对与 `tests/test_viewer_assets_contract.py` 共同保证）。模块文件必须以换行结尾，否则加载器直接报错 —— 粘连比失败更难查。原文件开头有一个 UTF-8 BOM 且它进入了交付文档，所以由加载器显式补回（`_VIEWER_JS_BOM`），源模块不含 BOM。

Phase 6B 之后"v1 回退"仅表示 renderer 语义回退，不表示回退整套 Viewer 文件（视觉层只有一套）。
