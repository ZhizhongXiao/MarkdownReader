# 浏览器验收（opt-in，Phase 5B）

默认 `uv run pytest -q` **不依赖浏览器**：这里证明的是 roadmap 里那句更强的验收 ——
「包含 Mermaid 的 HTML **离线打开后仍可正常显示**」。

```powershell
pwsh tools/run_browser_acceptance.ps1
```

脚本做的事：确认 `renderer/dist/renderer.cjs` 存在 → `npm ci` → `node --test`。

## 这个套件怎么验

```text
真实 adapter（dist/renderer.cjs）
        ↓  渲染 Mermaid 文档，拿到 html + resources.scripts
自己装配页面（模拟未来 assembler：把 runtime 与 boot 注入页面）
        ↓
Playwright 打开 file:// 页面
        ↓  拦截并记录**所有非 file:// 请求**（必须为 0）
断言 .mermaid 容器里真的生成 <svg>
```

## 用例

- **round-trip**：容器 DOM 文本 == 作者原文（Phase 4C 的 D2 不变式）。
- **三类图表**（flowchart / sequenceDiagram / gantt）：离线渲染出 `<svg>`。
- **mixed**：`invalid` 图在**前**、`valid` 图在**后** → 后者仍生成 `<svg>`，且没有 `unhandledrejection`、
  没有 `pageerror`、网络请求仍为 0。这是 `boot` 里「**每个容器各自** `run({ nodes: [node] })`」的实证：
  单个图失败不阻断同页面其它图。坏图最终呈现成什么 DOM 刻意**不冻结**（那是 runtime 自己的错误输出）。

因此它同时覆盖四件事：runtime 真的能跑、离线真的成立（零网络请求）、逐图故障隔离成立、
Phase 4C 的 escape 不变式在真实浏览器里成立。

## 浏览器从哪来

默认用**系统已安装的 Edge**（`channel: msedge`）：不下载浏览器，装个 `playwright` 包即可。

```text
MR_BROWSER_CHANNEL=chrome     # 改用系统 Chrome
MR_BROWSER_CHANNEL=chromium   # 用 Playwright 自带 Chromium（需先 npx playwright install chromium）
```

## Phase 5D：Python assembler 页面（同一条 opt-in 命令）

5B 证明的是「envelope → JS 测试里的模拟装配 → Mermaid 离线可渲染」；这里补的是**Python 装配层**：

```text
真实 adapter（dist/renderer.cjs）
        ↓  envelope（html + resources.styles / resources.scripts）
core/html_assembly.py（新 assembler，注入顺序 + 注入账本）
        ↓  最终 HTML（写盘）
真实 Edge 打开 file:// 页面，拦截所有非 file:// 请求
        ↓
断言 Mermaid 容器生成 <svg>、.katex 存在、本地图片是 data:image/png、
     非 file:// 请求为 0、无 pageerror、无 unhandledrejection
```

```powershell
uv run python tools/assemble_document.py --out build/smoke.html
pwsh tools/run_browser_acceptance.ps1 -ExtraPage build/smoke.html
```

这一步才会暴露 Python 装配层特有的问题：`<script>` / CSS 注入位置、HTML 序列化、runtime 与 boot 顺序、
是否漏了某个 resources 通道。不传 `-ExtraPage` 时该用例整条跳过，默认 5 项验收不变。

## 为什么它不在默认测试里

浏览器是平台工具，不是每次提交都必然存在的依赖；缺它时 pytest 不应假绿也不应阻塞。
所以这里是**显式**的 opt-in 命令，与 `tests/js`（jsdom viewer 契约）同级摆放、各自独立依赖。
