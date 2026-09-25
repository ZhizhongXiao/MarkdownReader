# MarkdownReader vscode-office Integration Roadmap

## 目标

本次升级不是重新开发 MarkdownReader，而是改变 Markdown 渲染能力的来源：

```text
旧：

MarkdownReader
→ 自行维护大部分 Markdown renderer


新：

vscode-office
→ 主要 Markdown 语义实现

MarkdownReader
→ adapter
→ standalone HTML
→ Viewer
→ Themes
→ GUI
```

目标是降低未来 vscode-office Markdown 能力变化带来的重复开发成本，同时保留 MarkdownReader 已经成熟的阅读体验和应用功能。

---

# Phase 0 — 冻结基线

## 任务

确认升级前版本能够稳定复现。

记录：

- Git commit；
- Git tag；
- Python 版本；
- Node 版本；
- npm renderer lockfile；
- 当前测试数量；
- 当前 demo HTML；
- onefile / onedir 打包状态。

不得修改用户可见行为。

## 验收

- 工作区 clean；
- baseline tag 存在；
- 当前测试能够运行；
- 当前真实 Markdown 可以转换；
- baseline demo HTML 可生成；
- Git 可以随时返回升级前状态。

---

## Phase 0 基线记录（2026-09-24 实测）

```text
baseline code commit   : d28f92394963a5f02e8d227667e1cd985afd0e9e
baseline tag           : pre-vscode-office-refactor-2026-09-24
refactor bootstrap HEAD: f37c8a2（AGENTS.md + docs/REFACTOR_ROADMAP.md）
Python                 : 3.12.10
Node                   : v24.20.0
npm                    : 11.19.0
uv run pytest -q       : 131 passed / 0 failed
node_renderer npm test : PASS（node --check render.js）
GUI 实机转换 smoke     : PASS（MarkdownReader.log 有真实生成记录）
demo baseline          : samples/demo.html 已入库
```

---

# Phase 1 — 建立迁移测试

在修改 renderer 前，增加兼容 fixture。

至少包含：

```text
basic markdown
heading
table
code
raw HTML
footnote
KaTeX
local image
remote image
cross-document md link
Front Matter

checkbox
mark
callout
wikilink
obsidian tag
Mermaid
PlantUML
```

其中目前 MarkdownReader 不支持的语法，可以作为“新 renderer 目标测试”，不能伪装成旧实现已经支持。

## 验收

明确得到两组契约：

```text
必须保持的旧能力
+
本次升级必须新增的 vscode-office 能力
```

测试必须能区分二者。

---

# Phase 2 — 接入 vscode-office 上游

目标目录：

```text
upstream/vscode-office/
```

优先采用 Git submodule。

上游代码原则上保持原样。

增加：

```text
tools/update_vscode_office.*
```

用于：

- 更新上游；
- 记录 commit；
- 检查 renderer 兼容；
- 运行升级验证。

如果使用 sparse-checkout：

> 初始化过程必须由脚本完整重现。

## 验收

新的源码 checkout 可以按照文档恢复相同 upstream 状态。

不得依赖开发者机器上某个手工复制目录。

---

# Phase 3 — 建立新 renderer adapter

建立：

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

旧：

```text
node_renderer/
```

暂时保留。

新 renderer 第一阶段只要求：

```text
Markdown
→ HTML fragment
→ headings
→ features
→ warnings
```

建议返回类似：

```json
{
  "html": "...",
  "headings": [],
  "features": {
    "katex": false,
    "mermaid": false,
    "plantuml": false,
    "checkbox": false,
    "callout": false,
    "wikilink": false,
    "mark": false
  },
  "warnings": []
}
```

## 验收

新旧 renderer 可以并行运行。

不得为了接入新 renderer 立即删除旧实现。

---

# Phase 4 — Markdown 能力迁移

逐项确定 ownership。

## 上游优先

- checkbox；
- mark；
- Callout；
- WikiLink；
- Obsidian tag；
- KaTeX；
- Mermaid；
- PlantUML；
- anchor。

## MarkdownReader 保留

- footnote；
- Markdown links rewrite；
- local images；
- remote resources；
- extra math compatibility；
- heading metadata；
- warning；
- standalone resource packaging。

每迁移一种能力都增加测试。

## 状态

```text
Phase 4A  PASS  checkbox / mark / callout / wikilink / obsidian-tag
Phase 4B  PASS  footnote / extra math delimiters / document links
parity     PASS  old/new 语义对照（D1 = 唯一接受的旧/新 parser 语义差异）
Phase 4C  PASS  Mermaid recognition/容器 + PlantUML 语义层（D2 = intentional export hardening）
adapter 覆盖：KEEP 15/15、TARGET 7/7、pending 0
production renderer 仍未切换（cutover 依赖 Phase 5 的 standalone resource closure）
```

证据：docs/MARKDOWN_COMPATIBILITY.md 的对应套件数字与 changelog。

## 验收

旧 MarkdownReader 已支持的 Markdown 不得出现功能倒退。

目标新增语法均可正确转换。

---

# Phase 5 — 资源收集与 standalone HTML

统一建立资源获取层。

处理：

```text
local images
remote images
CSS url(...)
KaTeX
Mermaid
PlantUML
theme assets
```

联网：

```text
尽可能内嵌
```

失败：

```text
保留 URL
warning
继续转换
```

Mermaid runtime 只有实际使用时加入。

PlantUML 当前只使用联网 server。

## 子阶段

```text
5A  静态资源 collector：protocol v2 + resource manifest、Markdown 本地图片、通用 CSS url() resolver、
    KaTeX CSS/fonts（自包含 build artifact）、failure warnings（不联网）
5B  Mermaid runtime：vendored runtime 按需注入 + 离线可用（opt-in 浏览器自动验收）
5C  Remote / network：remote images 与 PlantUML 抓取、超时/失败保留 URL + warning、断网仍转换
5D  standalone closure gate：外部子资源扫描 + 载荷纪律 + 体积报告
```

## 状态

```text
5A  PASS  protocol v2（resources 必在）+ `resources.items` manifest、Markdown 本地图片、
          通用 CSS url() resolver、KaTeX CSS/fonts 自包含 build artifact（dist/katex）、
          failure warnings；raw HTML 引用不内嵌；**仍不联网**
5B  PASS      vendored mermaid@11.15.0 runtime 经 resources.scripts 按需交付；每容器独立 run（逐图隔离）
              资产发布 staged + verified + rollback-protected（staging 复验 → .backup → 失败回滚）
              opt-in 浏览器验收：离线打开、零网络请求、.mermaid 内真的生成 SVG；含 invalid 在前 + valid 在后的 mixed 反证
5C  PASS      remote image 与 PlantUML 抓图：HTTP client（8s / 1 retry / 150ms / 16MiB / 只收 image）+ URL cache +
              并发 4 + 文档顺序写回；失败保留原 URL + warning + 转换继续；测试不访问公网（127.0.0.1 loopback）
              可靠性 closeout：body 读取阶段的 abort / socket 错误与 fetch 阶段同一分类（timeout / network 都可 retry，
              只有超限不 retry，且每次 retry 都是完整重新 GET）；timeout / retries / maxBytes 越界回落默认值
5D  PASS      standalone closure：新 assembler（core/html_assembly.py：注入顺序契约 + 注入账本）+
              closure checker（tools/standalone_closure.py：四态 verdict / 体积报告 / CLI，stdlib）
              可执行矩阵：真实 adapter + assembler + loopback，含两个反证（凭空注入的引用、manifest 说 inlined 却仍是外链）
              生产基线 samples/demo.html（1,544,529 B）strict 扫描 = standalone（checker 不搜 "http"）
              opt-in 浏览器 smoke：Python assembler 产出的集成页在真实 Edge 离线渲染（Mermaid SVG / KaTeX / data: 图片 / 零请求）
              checker closeout：srcset 按规范解析（不按逗号 split）、style 属性 CSS 参与扫描、
              证据按 occurrence 消费（degraded 先占位，author 声明不能遮蔽多余 occurrence）、
              link rel 判定（fetching token 优先于 metadata token）+ @import 字符串形式
cutover 是 5D 之后的**独立 checkpoint**，拆成一次只动一个架构层的 4 步：
C1  PASS      作者 raw HTML provenance 通道：renderer 在 token 层记录（renderer/document/author_references.js）
              → resources.author_references = [{ref, count}]（v2 additive；只记来源：不 fetch、不改 html、不进 items）
              checker 缺省自动消费该通道（--author-refs 仍可覆盖），佐证计数与 ref 抽取同路径（修 &amp; 实体失配）
              两侧共用 tests/fixtures/author_references.json：node 直测 scanner + spawn dist，pytest 走真实 dist
C2            生产适配器切到 v2：core/renderer_v2.py + core/renderer_node.py 显式版本配置（不再靠 JS 探测协议），
              并校验打包 Node >= 18
C3            converter 在 v2 选中时改用 core/html_assembly.py 装配；_theme_body_class 归 core/config.py；v1 逐字节不变
C4            默认 renderer 切换 + demo 再生 + 新产物过 standalone gate + release/selfcheck + rollback 证明
              前置：packaging/MarkdownReader.spec 目前不含 renderer/dist/（KaTeX + Mermaid 约 +5.5 MB）
production renderer 仍未切换（C2 起才动生产路径）
```

## 验收

普通 Markdown 不携带 Mermaid runtime。

包含 Mermaid 的 HTML 离线打开后仍可正常显示。

远程图片在联网转换成功时成为 standalone 资源。

断网转换仍成功。

PlantUML 网络失败不导致整个文档失败。

装配出的最终 HTML 有可判定的 closure verdict（standalone / degraded / author_references / failure）。

任何「应闭包却无证据」的外部 subresource 都会让 closure gate 失败。

---

# Phase 6 — Viewer 与 Theme 重构

将旧：

```text
templates/default/
templates/Modern/
templates/Office/
templates/Vscode/
templates/viewer.js
```

迁移为：

```text
viewer/
├─ viewer.html
├─ css/
└─ js/

themes/
├─ builtin/
│  ├─ modern/
│  ├─ office/
│  └─ vscode/
└─ template/
```

Viewer JS 拆为职责明确的小模块。

三个 builtin themes 永远内嵌进生成 HTML。

HTML 工具栏增加 Theme switcher。

Theme switching 不重新渲染 Markdown。

Dark/light 独立于 Theme。

## 验收

在同一 HTML 中可以即时切换：

```text
Modern
Office
VS Code
```

并保持：

- TOC；
- fold；
- scroll；
- light/dark；
- code copy；
- image lightbox；
- print；
- numbering。

现有 Viewer contract 全部通过。

---

# Phase 7 — External Theme

建立统一 Theme Registry。

Builtin 与 External 使用同一种 metadata / loader。

External themes：

```text
禁止 JS
禁止自定义 Viewer DOM
```

实现：

- theme validation；
- import；
- remove；
- assets inline；
- theme ID；
- metadata；
- Theme template。

项目内置：

```text
themes/template/
```

## 验收

可以导出 Theme template。

用户修改后可以重新导入。

生成 HTML 后，即使 MarkdownReader 中删除此外置主题，已经生成的 HTML 仍能正常使用它。

---

# Phase 8 — Config 持久化

废弃：

```json
"template": "modern"
```

改为：

```json
"external_themes": [
  "paper",
  "academic"
]
```

三个 builtin themes 不进入这个配置。

GUI 启动时：

```text
读取上次选择
+
扫描已安装 External Themes
→ 恢复主页面选择
```

不存在的 ID 自动忽略。

## 验收

重新启动 MarkdownReader 后：

> 主页面默认恢复上次选中的 External Themes。

---

# Phase 9 — GUI 设置页

GUI 保持轻量原生实现，不增加前端框架。

新增：

```text
Main page
Settings page
```

顶部 dark/light 控件附近增加 Settings 入口。

## Main page

负责：

- conversion；
- inputs；
- outputs；
- conversion options；
- selected external themes。

## Settings page

负责：

- external theme management；
- import；
- remove；
- export theme template；
- open theme location；
- storage information；
- about；
- remove MarkdownReader user data and exit。

不增加：

- clear cache；
- open logs；
- generic clear user data。

## 验收

主题管理和本次主题选择职责互不混淆。

---

# Phase 10 — User storage

实现统一 `core/paths.py`。

## Source

```text
.runtime/
├─ profile/
├─ assets/
└─ runtime/
```

## onedir

```text
MarkdownReader/
├─ MarkdownReader.exe
├─ _internal/
└─ data/
   ├─ profile/
   ├─ assets/
   └─ runtime/
```

## onefile

```text
%LOCALAPPDATA%/MarkdownReader/
├─ profile/
├─ assets/
└─ runtime/
```

其中：

```text
profile/config.json

assets/themes/external/
```

属于重要持久内容。

## 验收

业务模块不自行判断 PyInstaller 路径。

onefile 移动 EXE 后，配置和主题仍然存在。

onedir 删除整个目录即可完全清除。

---

# Phase 11 — 用户数据移除

只针对 onefile 持久目录提供：

```text
移除 MarkdownReader 用户数据并退出
```

确认弹窗必须清晰说明：

- config；
- external themes；
- runtime data；

都会永久删除。

确认按钮强制 disabled 5 秒。

取消始终可用。

确认后阻止 shutdown 重新写文件。

## 验收

操作完成后：

```text
%LOCALAPPDATA%\MarkdownReader
```

不存在或为空。

MarkdownReader 已退出。

EXE 本身保留。

---

# Phase 12 — Packaging

同时维护：

```text
onedir
onefile
```

两者来自同一 build definition。

不得维护两套已经漂移的 spec。

必须包含：

- bundled Node；
- renderer；
- builtin themes；
- Theme template；
- Viewer；
- required runtime assets。

## onedir

用于：

- 调试打包产物；
- 进一步开发验证；
- 文件级排错。

## onefile

用于：

- 日常使用；
- 发布；
- 便捷分发。

## 验收

两种包执行同一组 smoke tests。

---

# Phase 13 — Cleanup

只有新体系已经完全通过测试以后才：

- 删除旧 node renderer；
- 删除旧 template layout；
- 删除废弃 config；
- 删除兼容过渡代码；
- 更新 ARCHITECTURE；
- 更新 DESIGN；
- 更新 MARKDOWN compatibility；
- 更新 README。

不得提前清理。

---

# Final Acceptance Criteria

最终发布候选版本必须同时满足：

## Markdown compatibility

原 MarkdownReader 已支持能力无回归。

新增：

- checkbox；
- mark；
- Callout；
- WikiLink；
- Obsidian tag；
- Mermaid；
- PlantUML。

## Standalone

本地资源可离线。

联网远程资源尽可能内嵌。

远程失败有 fallback。

## Themes

HTML 至少包含：

```text
Modern
Office
VS Code
```

可即时切换。

External Themes 可按主页面选择加入。

## Persistence

上次选择的 External Themes 会恢复。

## GUI

Main / Settings 职责明确。

## Packaging

onedir / onefile 均通过真实 Markdown 转换。

## Upstream

vscode-office 可以通过明确流程更新。

更新上游不会要求复制和重新手工维护整套 Markdown parser。

## Tests

所有正式 tests 通过。

不得存在：

```text
为了发布而 skip 的失败测试
临时 xfail
注释掉的 assertion
```

除非有明确文档说明和批准。

---

# 每个 Phase 的执行方式

每次只处理一个 Phase。

AI 在开始编码前必须先输出：

```text
1. 当前 Phase
2. 已检查的相关文件
3. 本阶段目标
4. 明确不做什么
5. 预计修改文件
6. 测试方案
```

完成后输出：

```text
1. 修改内容
2. git diff 摘要
3. 测试结果
4. 尚未解决事项
5. 是否达到本 Phase 验收标准
6. 建议的下一 Phase
```

在用户确认之前，不自动跨越到下一个大阶段。