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
production renderer 后由 Cutover C4 切换（cutover 依赖 Phase 5 的 standalone resource closure）
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
C2  PASS      生产 bridge 能**显式**调用 v2：新 core/renderer_v2.py（artifact 存在性 / v2 冒烟 / subprocess 协议 /
              envelope 校验；导入无副作用，packaging spec 复用其 MINIMUM_NODE_MAJOR）+ core/renderer_node.py 的
              probe_node_version / _require_v2_node_major / dispatch（默认 v1；不探测协议；不回退 v1）
              v2 冒烟离线且要求 dist/katex 真的加载；返回完整 envelope（不压缩）；Node 下限 major >= 18
              未做：converter 仍不调用 v2（C3）、renderer/dist/ 仍未进发布包（C4）、无 config.json 配置项（Phase 8）
C3  PASS      converter 能显式走完整 v2 pipeline：process_single/process_batch 增加内部 renderer_version /
              renderer_options；v2 时 renderer 走 C2 bridge、装配交给 core/html_assembly.py
              warnings 合并顺序 = renderer + assembly（固定）；v2 内部默认 math + fetch 由 converter 写死并允许覆盖
              theme_body_class 收敛到 core/config.py（converter 与 assembler 共用）；runtime 不调用 closure checker
              未做：默认仍是 v1、demo 未再生、renderer/dist 未进发布包、release gate 与 rollback（全属 C4）
C4  A PASS     packaging closure：renderer/dist 进 spec 的 REQUIRED_FILES + datas + validate_release 的
              RUNTIME_FILES；release_freeze 在 PyInstaller 之前 npm ci + npm run build（只构建一次，两种形态共用）
              构建期用**将被打包的** node.exe 对 v1 与 v2 各冒烟一次
    B PASS    production policy = core/config.py::PRODUCTION_RENDERER_VERSION（现 "v2"）：converter 默认引用它，
              bridge 默认仍 v1，GUI 启动校验跟随 policy（validate_renderer_runtime_for）
    B' PASS   默认翻转后 triage：3 处测试假设（TOC href 的 unquote 归一化、batch 假 renderer 签名、默认==v1 的断言）
              + 1 处真漏洞（converter 对未知 renderer_version 静默按 v1 处理）→ 全部修正，未放宽任何 contract
    C PASS    7 项 TARGET 由 strict xfail 转为普通通过（xfail 清零）；markdown_fixtures 跟随 policy 且显式离线；
              demo 再生（1,544,529 → 1,547,612 B）并通过 standalone gate
    D PASS    onefile + onedir 真实构建，validate_release --mode both PASS（frozen 启动即验证 v2：包内 node + renderer/dist）
              浏览器验收 6/6；新验收记录 docs/QA-CHECKLIST-1.0.0-rc1-v2.md（0/43，待实机完成）
    剩余（用户侧）实机 QA 勾选 + 合并到 main 后 release_freeze --check-only / --tag
production renderer = v2（默认）；v1 = 显式回退路径（一处 policy 常量 + 完整打包资产）
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
├─ css/            layout.css + print.css
└─ js/             *.js + manifest.json（加载顺序的唯一来源）

themes/
├─ builtin/
│  ├─ base/        token（hidden，不可选）
│  ├─ modern/
│  ├─ office/
│  └─ vscode/
└─ template/       （Phase 7 外置主题开发模板）
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

### 状态

```text
6A  PASS    contract + asset loader consolidation
            docs/VIEWER_CONTRACT.md（KEEP 清单：DOM id / 存储键 / class / 两个独立状态 / file:// 单脚本约束）
            core/viewer_assets.py（外壳、viewer 脚本、打印样式、样式链、注册表的唯一来源）
            core/config.py 只留配置职责且不反向依赖；converter / html_assembly / gui.api 只经资产层取资产
            行为与产物不变：samples/demo.html SHA-256 不变（1018DB5A…F755，1547612 bytes）
            新增 tests/test_viewer_assets_contract.py（注册表 / hidden / 单主题内嵌 / 源码级 SSOT 锁）
                  tests/test_viewer_keep_contract.py（13 id + 8 存储键 + class/属性钩子冻结）
6B  PASS    资产搬迁 + viewer 源码拆分（行为零变化）
             viewer/viewer.html、viewer/css/{layout,print}.css、viewer/js/*（16 模块 + manifest.json）
             themes/builtin/{base,modern,office,vscode}/：目录名 == metadata.id == 选择器；三个主题 extends base
             core/viewer_assets.py 仍是唯一来源（两个根 + manifest 拼接 + BOM 归位）；config.py 的 TEMPLATES_DIR 删除
             viewer 载荷与拆分前逐字节相同（迁移脚本断言 + 回读校验）；samples/demo.html SHA-256 不变
             旧路径不再被 runtime / tests / packaging 引用；templates/index/ 原位
6C  PASS    每份 HTML 携带 base + modern + office + vscode；阅读器内即时切换
             CSS 定域：token + 组件规则 + print 规则（Office 85 处裸 body 收紧）
             html[data-theme-id] + body.theme-* 双条件；markdownreader-theme-id（全局，回落文档默认）
             初始状态与菜单进 shell（无 unthemed 首屏；已保存偏好 boot 后恢复）
             viewer/js/theme-switcher.js；contracts 22 → 30（THEME1–8）；浏览器 6 组合矩阵
             demo 1,547,612 → 1,574,223 B（+26.0 KiB）；真实打包 + validate_release PASS
6D  PASS    清理旧目录与文档收口（产物零变化）
             过期路径/术语收口：core 三处 docstring、README、ROADMAP、ARCHITECTURE、DEVELOPMENT、
             VIEWER_CONTRACT、MARKDOWN_COMPATIBILITY（K16/K17 + 验收覆盖表 current-state 单元格）
             templates/ 只剩索引页锁进静态守卫（旧路径黑名单 + 目录白名单）
             samples/demo.html 逐字节不变（BFD53709…，1,574,223 B）；531 passed / 0 xfailed
Phase 6 封板：6A 9bde750 / 6B d5b6b1b / 6C b7c372b + cc1bff9 / 6D 2a9f1c5
7A  PASS    core/paths.py：source .runtime/、onedir data/、onefile %LOCALAPPDATA%/MarkdownReader
             sys.frozen / _MEIPASS 只此一处（静态守卫）；config.json 的位置策略在 Phase 8B 落地（写 profile、不搬 legacy），
日志搬迁与 legacy 姿态在 Phase 10 收口（日志进 `runtime/`；legacy 成为一次性升级输入）
7B  PASS    统一 Theme Registry：builtin + assets/themes/external；builtin 优先、保留 ID 不可 shadow
             theme_ids()=已安装；builtin_theme_ids()=打包集；selectable_theme_ids(选中)；metadata files 声明
7C  PASS    契约先行（红）：校验规则 / 安装 / 删除 / 导出模板 / 资源内嵌 / 与 checker 的策略一致性
7D  PASS    实现：core/external_themes.py + themes/template/（真主题，导出即可导入）
7E  PASS    装配：theme_bundle() 统一两条路径；菜单带外置；账本 theme:<id>；阅读器零 JS 改动
7F  PASS    浏览器：真实 Edge 外置主题、零网络、删主题后仍可用；themes/template/ 随包 + validate PASS
Phase 7 封板：7A 3df3df6 / 7B a09e59d / 7C+7D e180651 / 7E 3d86e33 / 7F（本提交）
Phase 7 audit follow-up（远端审计 a910981 的 5 处阻断 + 3 处收口，两条提交）
  fix-1  d4b7736  消费时重新校验（validate_installed_theme）+ core/css_audit.py fail-closed 扫描器
                   validator / inliner / checker 共用扫描器；scope 必检；extends 收紧为 base|null
                   data MIME 白名单；realpath containment；载荷预算；三处 C4 前措辞
  fix-2  9ce5c4a  resolve_theme_selection() 成为 SSOT：bundle / menu / 账本 / warning 同源并进 report
  fix-3  第二轮审计：scanner 拒绝未审计的资源函数（image-set / -webkit-image-set / src / image / cross-fade / element）
                   theme_menu_markup(ids) 只消费 selection 快照（不再回扫 registry）；预算计入声明 CSS；_convert_v2 措辞
```

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

`template` **不废弃**：它一直是「文档默认主题 ID」，与外置主题列表是两个独立概念。

```json
{
  "build": {
    "template": "modern",
    "external_themes": ["paper", "academic"]
  }
}
```

```text
build.template         文档默认主题 ID（builtin，或当前可用的 external）
build.external_themes  本次生成额外携带的外置主题 ID 列表（builtin 永不进入）
```

配置读写归 core 所有：

```text
core/config.py  load_config() / normalize_config() / save_config()（原子写）
gui/api.py      set_configs() 只做 GUI 特有的路径规范化，然后委托 core
```

位置与读取顺序（Phase 8B）：

```text
显式 config_path > paths.config_path()（profile/config.json）
                 > PROJECT_ROOT/config.json（legacy）
                 > defaults
```

- 只写 profile；**不搬迁、不删除 legacy**（Phase 10 起 legacy 成为一次性升级输入：迁移成功即退场，
  见 Phase 10 落地记录）。
- profile 文件一旦存在就是权威：损坏时 warning + defaults，**不**回落 legacy。
- 落盘字段只限已有持久化语义的那些 + `build.external_themes`（`title` / `overwrite` 仍是运行期覆盖）。

GUI 启动时恢复选择（Phase 8C + audit follow-up；控件本身属 Phase 9）：

```text
get_theme_state() → default / installed / configured / selected / missing / invalid / warnings
```

```text
configured = config.json 记住的选择（持久事实，永不裁剪）
selected   = 其中当前已安装且通过 use-time gate 的子集（运行态，保持配置顺序）
missing    = configured 中当前不属于 installed registry 的 ID
invalid    = configured 中已安装、但当前 use-time gate 不通过的 ID
```

转换与状态**共用判断规则、不共用聚合语义**：`_classify_configured_theme()` 只判定单个 id；
`resolve_theme_selection()` 对 `invalid` 抛错（原异常原样传播，消息与排序不变），`theme_state()` 把它变成 warning
并继续分类其余 id。

主题暂时缺失时保留 `configured`，只在 `selected` 里忽略并给 warning（AGENTS §17）。
`template` 指向已删除 / 已损坏 / 非可选（如 `base`）的主题时保留配置值并给 warning，转换仍按 Phase 7 规则 hard failure。

`missing` / `invalid` 的边界由 registry 定义（Phase 8 audit follow-up #2）：registry 只认「目录可读、`metadata.json` 解析成非空 JSON object、metadata 未声明 hidden、id 不是保留名」的目录（根不是 object 与解析失败同类：warning + 跳过；metadata 缺失或为空 object 则安静跳过），因此 `missing` = registry 从未发现这个 id，`invalid` = 发现了但 use-time gate（目录名 == metadata id / slug / CSS 策略 / 体积预算）不通过；`invalid` 在转换侧仍是 hard failure。

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

## 状态

```text
9A  PASS  Phase 9A overall PASS（实现 + 契约 + 远端终审）
          主页面外置主题选择：GT1–GT14 + 静态守卫 2 项先红，桥接回归锁 3 项即时绿；follow-up 把
          GT15/GT16/GT18 由红转绿、GT13 扩展为「运行中 direct 调用也不改持久状态」、GT17 锁住
          「失败丢弃排队意图」；远端独立终审（对象 9a7063a）9A-1…9A-8 全 PASS
9B1 PASS  设置页 + 外置主题管理 + 存储信息 + 关于（GS1–GS13 + GS2b，共 14 条契约；主页「携带集合」与设置页
          「安装事实」两个状态机互不写入；返回主页先重读再显示）
9B2 NOT STARTED  9B closeout：`docs/USAGE.md` 存储位置收口、截图刷新、主页「坏但未配置主题仍可勾选」
                 是否顺带修正
Phase 10 PASS（remote seal = 04c30c2）
                 storage ownership 收口：log 与 WebView2 profile 进 `runtime/`；legacy config 变成一次性升级输入
                 （写完 profile 即退场，不再复活）。`47ea13f` 远端终审：P10-A PASS / P10-B PASS /
                 P10-C success path PASS / P10-C failed-save + corrupt single-read FOLLOW-UP REQUIRED
                 ⇒ 本地 follow-up 红→绿完成（2 failed / 18 passed → 20 passed）；远端独立终审对象 `04c30c2`
                 （failure-path snapshot / single-read / scope discipline 均 PASS）⇒ **Phase 10 overall PASS**。
Phase 11 实现完成（待远端复审）  用户数据移除 lifecycle：onefile-only 入口 + 5 秒确认 + terminal 状态
                 （单锁 operation gate，accepted 即关闭 file log 并 `window.destroy()`）+
                 `webview.start()` 返回后删 profile/assets/runtime/legacy 并 rmdir 空 root；
                 `core/user_data.py` 已落地
```

## 落地记录（Phase 9A：主页面外置主题选择）

设置页与它的入口整体留给 9B：9A 故意**不**引入 `#btn-settings`（避免一个尚无功能的临时产品状态），
并由静态守卫**反向断言** `btn-settings` / `settings-page` / `import_theme` / `remove_theme` /
`export_theme_template` / `open_theme_location` 都不出现在 `gui/assets/` 中。

UI 形态、写入语义与串行化规则先以红契约冻结（`GT1–GT14` 14 项 + 静态守卫 2 项 = 16 项真红；
`tests/test_gui_theme_state_contract.py` 3 项是既有语义的桥接层回归锁，预期即时绿），再实现：

```text
行状态（四态封闭，全部推导自桥接字段，绝不解析 warning 文本）
  selected   可选且在工作集内 → 勾选、可改
  available  可选但不在工作集内 → 未勾选、可改
  missing    ∈ missing → 未勾选、不可改（保留在列表，带「移除」）
  invalid    ∈ invalid → 未勾选、不可改（保留在列表，带「移除」）

工作集写入规则
  初始       = configured 原样副本（configured 是记忆，永不隐式裁剪）
  check(X)   → 追加到末尾（既有条目相对顺序不变）
  uncheck(X) → 只删除 X
  remove(X)  → 只删除 X，且只对 missing / invalid 提供
  保存       → { external_themes: 完整工作集 }（不是 selected；9A 只写这一个键）
  串行化     → 至多 1 个在途写；后续改动合并为最新；旧 payload 不会覆盖新 payload
  保存失败   → 丢弃未确认的假定态 → get_theme_state() → 以后端状态重建 → ERROR 日志
```

选择只有一条生效通道：`config.json` 的 `build.external_themes`（`converter._selected_external_themes(cfg)`
→ `html_assembly.assemble_document()` → `resolve_theme_selection()`），因此 `convert` 请求形状不变
（`GU1` 的 7 键保持绿），`gui/api.py` 与 `core/**` **零改动**。转换在途时整面冻结（与模板下拉同一把锁）。

证据：全套 `uv run pytest -q` = **654 passed / 0 failed / 1 skipped**（+6 = 3 项静态守卫 + 3 项桥接回归锁）；
GUI 契约 `GUI_CONTRACTS {"pass": 23, "xfail": 0, "xpass": 0, "fail": 0}`、`GUI_CONTRACT_RECORDS 23 of 23`；
红阶段为 23 条中 14 条失败（`assert 14 == 0`）+ 静态守卫 2 项失败；ruff 全绿；`samples/` 逐字节未动。
**未做**：设置页（9B）、主题导入/删除/导出模板的桥接方法与 UI、`remove-user-data` 流程（9B 先做 user-data ownership 侦察）、
`docs/USAGE.md` 的存储位置收口、截图更新（记为 KNOWN STALE）、`_write_output(newline="\n")` 卫生债。

## 落地记录（Phase 9A follow-up：确认持久化先于转换 —— 远端审计发现）

远端审计（`cf7be38`）判定 **9A-4 / 9A-5 / 9A-6 = FOLLOW-UP REQUIRED**，原因是三处窄缺口；本 follow-up 全部收口
（**`9a7063a` 已推送并通过远端独立终审：9A-1…9A-8 全 PASS，production semantics / contract coverage /
scope discipline 均 PASS ⇒ Phase 9A overall PASS**）：

```text
F1  主题保存与转换之间没有 happens-before：pywebview 的每个桥接调用各跑一个线程，而
    set_configs 是 load→update→save（无跨调用锁），因此「主题写」与「run 自己的写」重叠会丢更新，
    也可能出现「配置已新、本次转换仍读旧 selection」（convert 的 7 键请求不携带主题列表）。
    修复：drainThemeSaves() 返回 true|false；waitForThemeSaves() 把「是否已确认落盘」交给 runConvert()，
    run 在 setConversionRunning(true) 之后、任何桥接调用之前等待；false（写失败）→ ERROR +
    取消本次转换（不再用旧配置继续生成）。「队列停了」不等于「选择已落盘」。
F2  「已选 N」摘要读的是启动快照 state.selected，而 checkbox 来自工作集 _themeSelection，
    勾选后摘要不动。修复：selected 计数 = themeRowState(id) === "selected" 的行数（missing/invalid 不计入）。
F5  save 失败后 reload 也失败时，异常从「未被 await 的 drain」逃出（unhandled rejection），
    界面还停留在未确认的 optimistic 状态。修复：新增 _themeConfirmed（最近一次确认落盘的选择，
    由成功保存或桥接状态更新），reload 失败 → ERROR + 回到 _themeConfirmed（**不回退启动快照**，
    它可能早于一次已经成功的保存）。
```

契约（红 → 绿；计数锁 23 → 27，GT13 只扩展不增记录）：

```text
GT15（红）conversion waits for confirmed theme persistence —— 双分支：写在途时 run 不发任何请求，
           落定后才 prepare_conversion → run set_configs → convert；写被拒则三者都不发生、转换锁释放、
           界面回到桥接状态、随后仍可用
           （红证据口径：该 record 红是因为 **success branch** 的断言先失败；failure branch 当时未被
           独立观察为 red，现在由正式 green 契约覆盖 —— 不把历史写成「两个分支分别红过」。）
GT16（红）summary 跟随 working selection（1 → check → 2 → uncheck → 1）
GT17（绿）A 在途、B 到达、A 被拒 → B 不再发出、发生 get_theme_state、optimistic 状态被完整替换
           （既有行为的回归锁）
GT18（红）save 成功建立 confirmed → 再改被拒 → reload 也失败 → 回到 last confirmed（不是启动快照）、
           ERROR×2、无第三次写、队列随后仍可用
GT13（扩展）运行中 direct toggleExternalTheme / removeConfiguredTheme → 行不变、无新写入
```

证据：红阶段 `GUI_CONTRACTS {"pass": 24, "xfail": 0, "xpass": 0, "fail": 3}`、`GUI_CONTRACT_RECORDS 27 of 27`，
三条红分别停在对应缺失行为的断言上（`gui.test.js` `:747` / `:816` / `:870`，失败原因逐条确认为功能缺失
（其中 GT15 停在 success branch 的断言 —— failure branch 当时未被独立观察为 red），
其中 GT17 初版曾因契约自身的 harness auto-resolve 误报，已按 GT8 的方式改为 `autoThemeState: false`）；
实现后 `GUI_CONTRACTS {"pass": 27, "fail": 0}`、`27 of 27`；全套 `654 passed / 0 failed / 1 skipped`
（契约增加不新增 pytest 函数 ⇒ 总数不变）；ruff 全绿。本次只动 `gui/assets/gui.js`、
`tests/js/gui.test.js`、`tests/test_gui_state_contract.py`（+3 份文档）；`gui/assets/{index.html,gui.css}`、
`gui/api.py`、`core/**`、`packaging/**`、`viewer/**`、`themes/**`、`samples/**` 均未改动。

证据边界：以上（`654 passed / 1 skipped`、`GUI_CONTRACTS 27 of 27`、ruff 全绿）都是**本地**证据；远端
combined status 为空（本仓库没有 CI），因此不把 pytest / ruff 结果写成远端执行结果 —— 远端只做静态终审
（拓扑、diff 面、契约与文档口径）。终审对象是 `9a7063a`（终审时的远端 HEAD）；其后 HEAD 前进到
`7358b87`（`chore(lint): reach zero diagnostics under the agreed MCP and pyright gates`，22 文件的
lint/类型口径收口，不改变 9A 语义，另行记录、不并入 9A 的改动面）。

## 落地记录（Phase 9B1：设置页壳 + 外置主题管理 + 存储/关于）

9B 先做了一轮只读的 user-data ownership 侦察，结论是**现在不能实现「移除用户数据并退出」**：日志仍在
`application_dir()/MarkdownReader.log`（三种布局下位置各不相同，onefile 还会落在 EXE 旁边）、WebView2
profile 仍是 `%LOCALAPPDATA%\MarkdownReader\WebView2`（破坏 onedir「删掉整个目录即完整移除」）、legacy
`config.json` 会在删除 profile 之后被下一次启动重新读入（配置「复活」）。因此 9B 拆成 9B1（本次）与 9B2
（closeout），并且**不做**「移除用户数据」的任何形式 —— 包括 disabled 占位按钮与 5 秒确认流程。

```text
设置面（本次交付）
  设置入口        头部 dark/light 旁边；整页 overlay（默认 hidden，返回按钮关闭），workspace tab 状态不受影响
  外置主题管理    installed 清单（逐 id 的 valid + reason）、导入、卸载、导出模板、打开主题目录
  存储信息        运行模式 + user_data_root / config_path / external_themes_root / runtime_root
  关于            应用名、版本（唯一运行时来源 core.version）、渲染器版本、Python、运行模式

两个状态机（AGENTS §17，互不替代）
  主页    get_theme_state()      「本文档携带哪些」：configured / selected / missing / invalid
  设置页  get_theme_inventory()  「这里装了什么、是否仍可用」：installed[] + valid/reason
  写入    设置页四个动作一律不写 config；卸载只删安装副本，configured 原样保留 → 主页随后报 missing
  串行    转换在途时四个动作与主页控件一起冻结（direct 调用也不触达桥接）；返回主页重读 get_theme_state()
```

契约（GS1–GS13 + GS2b，共 14 条，红 → 绿）：

```text
GS1  settings shell：入口开页；返回后 workspace tab 与携带集合摘要不变
GS2  inventory 逐 id 报有效性（fixture 里的坏主题故意不在 configured 中）
GS2b inventory 只在开页时读取（启动路径与既有契约计数不变）
GS3  导入走桥接、成功后重读 inventory、不改携带集合
GS4  被拒/异常的导入如实报错且页面仍可用（不留未处理 rejection）
GS5  卸载只发 remove_theme：configured 不动、无 set_configs
GS6  导出报告写出的路径；被拒时报告而不是静默
GS7  全新环境打开主题目录：走「创建后打开」，失败也报告
GS8  存储信息逐字渲染桥接回复（页面不得写死路径）
GS9  关于逐字渲染桥接回复（版本不得是页面字面量）
GS10 运行中的转换冻结管理面（含 direct-handler guard）并在结束后解锁
GS11 设置面任何动作都不写携带集合（set_configs 计数为 0）
GS12 返回主页**先重读再显示**：pending 期间设置页仍在前面、Back 被拒；失败则留在设置页 + ERROR，
     Back 可重试（重试真的再读一次）
GS13 联合契约：import_theme / export_theme_template 必须是 (self, request)
```

证据：红阶段 `GUI_CONTRACTS {"pass": 27, "xfail": 0, "xpass": 0, "fail": 14}`、`GUI_CONTRACT_RECORDS 41 of 41`，
全套 `10 failed / 654 passed / 1 skipped`（失败逐条确认为功能未实现：缺 `#settings-page`、缺 7 个桥接方法、
缺 `core.version`）；实现后 41/41 全绿（无 fail/xfail/xpass）、全套 **664 passed / 0 failed / 1 skipped**、
ruff 全绿、pyright（项目 standard）81 文件 0 error。
改动面：`core/version.py`（新）、`core/external_themes.py`（+`ensure_theme_root` / `theme_inventory`）、
`gui/api.py`（+7 个桥接方法）、`gui/assets/{index.html,gui.js,gui.css}`、6 个测试文件（2 个新增）与三份文档；
`viewer/**`、`themes/**`、`renderer/**`、`packaging/**`、`samples/**` 均未改动。
**未做**：`remove user data` 流程（含占位与倒计时）、日志迁移、WebView2 迁移、legacy config 治理、
Phase 10 filesystem cleanup、`core/user_data.py`、`docs/USAGE.md` 存储位置与截图（归 9B2）。

**9B 新发现 follow-up**：`theme_state()["invalid"]` 只分类 configured 的 id，因此「已安装、被手工改坏、又从未
被选中」的主题在主页仍显示为可选，要到下一次转换才 hard fail。设置页不受影响（逐 id 跑 use-time gate）；
是否顺带修正主页留给 9B2，不改写 Phase 8/9A 的历史语义。

**远端复审（对象 `b58cdbd`）**：inventory / core / bridge / management boundary / storage / about 判定 PASS，
但 `closeSettings()` 的「先隐藏、再异步重读」判定 **FOLLOW-UP REQUIRED** —— 存在「主页已可交互、行的状态仍是
stale」的窗口，而 GS12 当时只证明「最终会重读」，不证明「可见切换发生在重读之后」。窄修复：新增
`_settingsClosing`，关闭期间设置页保持在前、Back 与四个管理动作按 state 拒绝（不只是 disabled DOM），
`await reloadThemeState()` 成功后才隐藏；失败则留在设置页并记 ERROR，Back 即重试（重试真的再读一次）。
GS12 相应升级为「先重读再显示」的判别契约（含失败支路），record 数不变（仍 41）。

---

# Phase 10 — 剩余 user-storage 迁移与治理

`core/paths.py` 已在 Phase 7A 落地，`profile/config.json` 已在 **Phase 8B** 起成为权威配置位置
（读取顺序：显式路径 > profile > legacy > defaults；不自动搬迁 legacy）。本阶段收尾剩余部分：

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

## 落地记录（Phase 10：storage ownership 收口）

Phase 9B 的 ownership 侦察留下三笔债，本次一次收口。生产面只动 `core/paths.py`、`core/logger.py`、
`core/config.py`、`gui/app.py`。

```text
P10-A  log           application_dir()/MarkdownReader.log → paths.log_path() = runtime_root()/MarkdownReader.log
P10-B  WebView2      %LOCALAPPDATA%/MarkdownReader/WebView2 → paths.webview_storage_root() = runtime_root()/WebView2
P10-C  legacy config 永久 fallback → 一次性升级输入（parse → save(profile) → 只有成功才 remove legacy）
```

三种布局的最终形态（`core/paths.py` 是唯一来源）：

```text
source   <repo>/.runtime/{profile/config.json, assets/themes/external/, runtime/{MarkdownReader.log, WebView2/}}
onedir   <app>/data/{profile,assets,runtime{log,WebView2}}
onefile  %LOCALAPPDATA%/MarkdownReader/{profile,assets,runtime{log,WebView2}}
```

legacy 的冻结语义（无 tombstone；「一次性」由 profile 的存在承担）：

```text
profile 存在                  → 只读 profile；legacy 连解析都不做（handled = false）
profile 缺失 + legacy 缺失（handled = false）     → defaults
profile 缺失 + legacy 可解析   → 迁移：对**一次读取**得到的 snapshot 调 save_config(_parse_config_object(...))
                              → 成功后才 os.remove(legacy)；本次直接用这份 snapshot（不再读 legacy）
profile 缺失 + legacy 不可解析  → defaults + warning（handled = true / snapshot = None）；不写 profile、不删 legacy、不重读
写 profile 失败（P10-14）      → 本次直接用第一次读取的 snapshot（**不再重读 legacy**）；保留 legacy；不 remove；warning；下次可重试
删除 legacy 失败（P10-12）     → warning；profile 已是权威，永不复活；本次用的是同一份 snapshot
```

实现要点（对应复审的五件事）：

```text
save_config 失败绝不 retire   save(parsed) 先于 os.remove；失败即 return，legacy 原样保留
retire 失败后 profile 永久优先 删除失败只 warning；profile 已存在 ⇒ _find_config 永不回落到 legacy
_find_config 仍是查询        一次性迁移在私有 _migrate_legacy_config_if_needed()，只由 load_config() 在
                              未传显式路径时调用（显式路径是一次性输入，不得改写用户数据）
logger/WebView2 三布局进 runtime  两个 resolver 都建在 runtime_root() 之下；logger 在 setup_logging()
                              时刻创建目录（解析保持无副作用），GUI 只把 resolver 的结果交给 webview.start()
gui/app.py 失去自行判断能力     删除 get_webview_storage_path()；静态守卫把 LOCALAPPDATA/APPDATA 的
                              ownership 收回 core/paths.py
```

配置只读一次：私有 `_read_config_object()` 是**唯一**把配置文件变成 JSON 的地方（区分「合法空对象 `{}`」与
「解析失败」），`_parse_config_object(data)` 把已解析对象转成 flat config，`_parse_json()` 只是二者之和。
迁移因此使用**同一份 snapshot**（不再重读 legacy），并由私有 helper 以 `(handled, snapshot)` 交回
`load_config()`：`handled` 让本次不再调用 `_find_config()`，所以**成功 / 写失败 / 不可解析**三条支路都只真实读取
legacy 一次，也消掉了「第一次确认过的值被第二次读取替换」这一窗口；sectioning / normalization / 原子写仍只由
`save_config()` 一处负责，不新增第二套 writer。

证据：红阶段 16 failed / 31 passed（P10-9 的红签名 = `assert 'office' == 'modern'`，即删掉 profile 后旧值复活的
实证；P10-14 的红签名只有「失败必须被报告」这条不成立）；实现后**四个契约文件 54 passed**、全套 **693 passed / 0 failed /
1 skipped**、ruff 全绿、pyright（项目 standard）82 文件 0 error、MCP `python_review` 11/11 批 `batch_ok` 且末批
`scope_complete`。`gui/api.py::get_storage_info()` 的 shape 未变（它本来就取 `core.paths` 事实，设置页因此自动
显示新的 runtime truth）。

**audit follow-up（远端终审对象 `47ea13f`）**：P10-A / P10-B 与 P10-C 的成功支路 PASS，但 P10-C 的**失败支路**
FOLLOW-UP REQUIRED —— 冻结语「写失败时本次仍用已解析的 legacy 内容」当时并不严格成立：迁移返回后 `load_config()`
仍会 `_find_config()` 再找到那个 legacy 并 `_parse_json()` 读第二遍，于是本次用的是**第二次**读取（两次之间文件被改成
`vscode` 或改坏，第一次确认过的 `office` 就被替换）；corrupt 支路同样重复读取、重复 warning。
窄修复（不改公开 API、不扩大范围）：私有 `_migrate_legacy_config_if_needed()` 返回 `(handled, snapshot)`，
`load_config()` 在 `handled` 时直接 `cfg.update(snapshot)` 而不再 `_find_config()`；`_find_config()` 的查询性质、
`save_config` 恰好一次、flat config 入参、显式路径不触发迁移、`RUNTIME_NOTE` 与三份文档的既有结论全部不变。
判别契约（先红后绿，本地证据）：corrupt 支路数真实读取次数 `assert 2 == 1` 且同一条 warning 出现 2 次；failed-save
支路在 mock `save_config()` 里**先把 legacy 改成 `vscode` 再抛 `OSError(28)`**，旧实现红签名 `assert 'vscode' ==
'office'`，新实现继续用第一次的 snapshot `office`；成功支路与 retire-failure 支路也各锁 1 次读取。红阶段
2 failed / 18 passed（`tests/test_config_contract.py`），修复后 20 passed、四个契约文件 **54 passed**、全套
**693 passed / 0 failed / 1 skipped**、ruff（项目闸 + MCP 规则集）0、pyright 0 error、MCP `python_review` 本批
`batch_ok` 且 `scope_complete`。

远端独立终审对象 `04c30c2`（本 follow-up 的提交）：failure-path snapshot / single-read / scope discipline 均 PASS
⇒ **Phase 10 overall PASS**（Phase 10 封板于 `04c30c2`）。

**未做**（按阶段顺序）：`remove user data` 按钮与 5 秒倒计时、terminal deletion、`core/user_data.py`、
9B2 截图刷新、未 configured 坏主题的主页修复、`_write_output` newline 债。

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

## 落地记录（Phase 11：onefile 用户数据移除）

只有 onefile 需要这个动作：onedir 的承诺仍是「删掉整个目录即完整移除」，source 是工作树。生产面在
`core/user_data.py`（新）、`core/config.py`、`core/logger.py`、`gui/api.py`、`gui/app.py` 与
`gui/assets/{index.html,gui.js,gui.css}`。

冻结语义（P11-1…P11-11 的落地形态）：

```text
顺序        request accepted → terminal flag（单锁内，只置一次）→ close_file_logging()
            → window.destroy() → webview.start() 返回 → remove_user_data() → main 返回
删除集合    profile_root / assets_root / runtime_root 递归删除 + legacy config 单文件
            user_data_root 只 rmdir（绝不当递归目标）；缺失目标 = no-op，不记 failure
失败语义    某路径删不掉 → failed=[{path,error}] 且 ok=false；root 非空同样记 failure
            重试有界（约 2s deadline / 200ms），耗尽即上报，绝不谎报、绝不重建
非 onefile   `remove_user_data()` 第一行自己拒绝：source / onedir 一次删除都不做，报告
            ok=false + error（onefile-only 是 core 的前提，不是调用者必须记得的责任）
destroy 失败  `_destroy_window()` 返回成功与否；失败则回滚 `_removal_requested` 并回
            `{ok:false, error:"无法关闭窗口，用户数据未删除。"}` —— 页面用既有的 GR7 机制自动
            解锁并可重试；file logging 保持关闭（明确失败后的降级状态，不引入 reopen 生命周期）
日志        `close_file_logging()` 幂等，并把 logger 置为终止态：之后 `setup_logging()`
            不得再打开文件（AGENTS §23「确认后禁止日志写入」因此严格成立）
桥接        public surface 只新增 `request_user_data_removal()`；它只结束会话、不删文件，
            内部 `_should_remove_user_data_on_exit()` 是 gui.api → gui.app 的生命周期 seam
原子 gate   一把 `threading.Lock` 同时保护 `_removal_requested` 与 `_operations_in_flight`；
            每个入口（set_configs / import / remove / export / open_theme_location / convert /
            prepare_conversion / 三个 native dialog / 读 owned storage 的 get_config 等）
            都先过 `_operation()`，dialog 先过 gate 再取 dialog 锁（消除 check-then-act 窗口）
capability  `get_storage_info()` 追加 `removal_available` / `removal_items`（config /
            external-themes / runtime 三项事实），页面据此渲染入口与清单，不猜 frozen 布局
UI          onefile 才显示入口；确认弹窗列三项 + 5 秒倒计时（Confirm 初始 disabled、
            Cancel 全程可用、重开重新计满）；确认后 terminal UI lock；backend 显式返回
            `{ok:false}` 时回滚 provisional lock（弹窗保持、无需二次倒计时、可直接重试），
            只有结构化拒绝回滚 —— Promise rejection 不回滚（accepted 请求本就会销毁窗口）
```

实现细节：`core/config.py` 把 `_legacy_config_path()` 提升为公共 `legacy_config_path()`（删除残留
不重新推导路径，`PROJECT_ROOT` 仍是它的 seam）；`core/logger.py` 的终止态是模块级事实；
`gui/api.py` 的 `convert()` 拆出 `_convert()`，让 gate 保持在入口而不是埋在长方法体里。

证据：红阶段 28 failed / 692 passed / 1 skipped（27 条新/翻转契约红 + JS wrapper 因 6 条 GR 红），
JS `tests 47 / pass 41 / fail 6`；实现后 JS **47/47**、聚焦契约 **54 passed**、全套
**726 passed / 1 skipped / 0 failed**、ruff（项目闸 + MCP 规则集）全绿、pyright（项目 standard）
0 error、MCP `python_review` 分页 `batch_ok` 至 `scope_complete`。

**audit follow-up（远端终审对象 `e7a71ed`）**：主架构 PASS，但两处窄缺口被点名，均已在本地修好（待复审）：
（1）**显式拒绝后的 UI 死锁**：backend 完全可能正常返回 `{ok:false, error:"仍有操作在执行"}`（例如某个
`prepare_conversion` 还在 gate 里），而前端此前把 `_removalTerminal` 置位后不看 reply —— 窗口不会销毁、
删除不会发生，用户却被永久锁死，违反「backend 才是 authority」。现在 `confirmUserDataRemoval()` 在收到
**结构化 `{ok:false}`** 时回滚 provisional lock（弹窗保持可见、无需二次倒计时、可直接再次 Confirm，第二次
确实发出第 2 个请求）；**Promise rejection 不回滚**，因为 accepted 请求本来就会销毁窗口。
（2）**core 破坏性守卫**：`remove_user_data()` 自身此前不检查 `removal_available()`，source/onedir 上被直接
调用会去删 `<repo>/.runtime/**` 与仓库根 legacy config。现在第一行就拒绝并返回
`{ok:false, removed:[], failed:[], user_data_root_removed:false, error:…}`，**任何 filesystem deletion 都不发生**。
判别契约（先红后绿）：`test_the_deletion_refuses_a_layout_it_does_not_offer[source|onedir]` 红签名是
`{'ok': True, 'removed': [...], 'user_data_root_removed': True}`（旧实现真的触达 deletion spy）；`GR7` 红签名是
`the page works again once the backend refuses`（`tests 48 / pass 47 / fail 1`）。修复后聚焦契约 **56 passed**、
JS **48/48**。

（3）**destroy 失败的语义**：`window.destroy()` 抛异常时旧实现只记 warning 却仍回 `{ok:true}`，于是
terminal flag 保持、窗口仍活、`webview.start()` 不返回 ⇒ 既没删除也没退出、GUI 还锁死。现在
`_destroy_window()` 返回成功与否，失败时回滚 `_removal_requested` 并回 `{ok:false, error:"无法关闭窗口…"}`，
页面用既有的 GR7 机制解锁并可重试第二次（第二次 close 成功即 `ok:true`）；file logging 保持关闭 ——
这是明确失败后的降级状态，不为它引入 reopen 生命周期。判别契约（先红后绿）：
`test_a_window_that_cannot_be_destroyed_is_an_explicit_refusal` 红签名是 `{'ok': True, 'error': ''}`
（destroy 抛 `RuntimeError` 仍被当成成功）；修复后聚焦契约 **57 passed**、JS **48/48**（无需新增 JS 契约，
GR7 已覆盖全部结构化拒绝的恢复）。

**未做**（9B2 分界）：`docs/USAGE.md` 存储位置与截图刷新、主页「坏但未配置主题仍可勾选」、
`open_theme_location` 的返回值形状清理、`_write_output` newline 债。

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