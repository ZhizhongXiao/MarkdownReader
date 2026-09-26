# Base 基础主题

`base` 只提供主题 token：调色板（亮/暗两套）、字体与布局尺寸变量（`--sidebar-width`、
`--content-max-width`、字号、行高）。阅读器外壳、布局样式与交互都在 `viewer/`，不属于任何主题。

它是**全局回落**：`:root` 与 `[data-theme="dark"]` 不 scoped，任何主题没有定义的 token 都由它兜底。
可选的三个主题则相反 —— 它们的 token、组件规则与打印规则必须 scoped 到 `html[data-theme-id="<id>"]`，
因为每份生成 HTML 都同时携带三套主题（Phase 6C）。

三个内置主题都继承它（`modern` / `office` / `vscode` 的 `metadata.json` 里 `extends: "base"`），
它自身 `hidden: true`，因此不出现在用户可选的主题列表里。

面向用户时通常选择：

- `modern`：通用现代阅读器
- `office`：正式文档与打印
- `vscode`：编辑器预览风格的技术阅读

不要在基础主题里加入强烈品牌化或特定文档风格，把这些规则放进具体主题。
目录的标题提取与编号拆分由 Python 与 Node 生成层完成；目录行结构由共享布局样式承载。
