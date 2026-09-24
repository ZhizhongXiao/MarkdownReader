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

因此它同时覆盖三件事：runtime 真的能跑、离线真的成立（零网络请求）、
Phase 4C 的 escape 不变式（DOM 文本 == 作者原文）在真实浏览器里成立。

## 浏览器从哪来

默认用**系统已安装的 Edge**（`channel: msedge`）：不下载浏览器，装个 `playwright` 包即可。

```text
MR_BROWSER_CHANNEL=chrome     # 改用系统 Chrome
MR_BROWSER_CHANNEL=chromium   # 用 Playwright 自带 Chromium（需先 npx playwright install chromium）
```

## 为什么它不在默认测试里

浏览器是平台工具，不是每次提交都必然存在的依赖；缺它时 pytest 不应假绿也不应阻塞。
所以这里是**显式**的 opt-in 命令，与 `tests/js`（jsdom viewer 契约）同级摆放、各自独立依赖。
