# 迁移兼容矩阵

本页记录 `vscode-office` 迁移期间**每条能力的迁移状态**：它属于哪一类、由哪个测试证明、按路线图何时改变。

## 三份文档的分工

| 文档 | 作用 |
| --- | --- |
| [兼容范围](MARKDOWN.md) | 用户可见的当前 Markdown 行为（唯一来源） |
| **本页** | 迁移状态：KEEP / TRANSITIONAL / TARGET / IMPLEMENTATION DETAIL 分类与证据 |
| `tests/fixtures/markdown/` + `tests/test_markdown_*` | 上面两页的**证据** |

本页不描述产品行为细节，行为细节一律以 [兼容范围](MARKDOWN.md) 与真实代码为准。

## 分类与判定规则

| 分类 | 含义 | 允许什么 |
| --- | --- | --- |
| **KEEP** | 长期必须保持的产品行为 | 断言写成用户可见语义或关系，不写渲染器内部实现 |
| **TRANSITIONAL** | 今天的真实行为，但路线图已明确要改 | 必须有测试记录，并登记“由哪个 Phase 改写” |
| **TARGET** | 今天不存在、本次升级要新增 | Phase 1 用 `xfail(strict=True)` 作迁移门禁，只锁产品级语义 |
| **IMPLEMENTATION DETAIL** | 允许未来重构 | **不得**写成永久 KEEP 断言 |

判定原则：**换掉 renderer 之后，用户还能不能看出差别**。看不出差别的，就不是 KEEP。

## KEEP：必须保持

| # | 能力 | 证据 |
| --- | --- | --- |
| K1 | heading/TOC 链路：id 非空唯一、metadata `anchor` = 正文 `id`、TOC `data-id` = 正文 `id`、`href` 可解析回同一 heading、H1–H6 level、围栏文本不入 TOC、尾随 `#` 不入正文、重复标题 id 不冲突、中文/标点/emoji/空标题不断链 | `tests/test_markdown_anchor_contract.py`（8 项） |
| K2 | 行内基础与文本转义（`<`、`&`） | `test_markdown_compat_keep.py::inline-basic` |
| K3 | `breaks:false`：单个换行不产生 `<br>` | `keep/paragraph-breaks-off` |
| K4 | `typographer:false`：引号、破折号、省略号不被替换 | `keep/typographer-off` |
| K5 | GFM 表格与列对齐 | `keep/table-alignment` |
| K6 | 围栏代码块与语言标注 | `keep/code-fence-language` |
| K7 | 原始 HTML 行内与块级原样保留 | `keep/raw-inline-html` |
| K8 | 脚注（引用、脚注区块、返回链接） | `keep/footnote` + `test_renderer_links.py`；**adapter 侧 Phase 4B 已覆盖**：由 MarkdownReader-owned `markdown-it-footnote@^4.0.0` 承担（pinned 上游没有实现），证据 `test_renderer_adapter_compat.py` |
| K9 | KaTeX 预渲染：出现公式时得到 KaTeX HTML。`$…$` / `$$…$$` 属 pinned 上游 KaTeX 插件；`\(…\)` / `\[…\]` / `\begin{env}` 由 MarkdownReader math compat 解析，但 **token 类型与渲染仍属上游** | `keep/math-inline-display` + `test_renderer_katex_assets.py` + `test_renderer_adapter_compat.py` |
| K10 | Front Matter 只作 metadata，默认不进正文 | `test_front_matter.py`、`test_conversion_edge_cases.py` + `keep` 语料不含 front matter 的保证 |
| K11 | `fuzzyLink:false` 的既有语义：裸文件名与版本号保持文本 | `test_renderer_linkify.py` |
| K12 | `.md` / `.markdown` → `.html` 文档关系（含 fragment/query、未入清单 warning、消息可读） | `test_renderer_links.py`、`test_converter_integration.py`；**adapter 侧 Phase 4B 已覆盖**（`renderer/document/links.js`，parse 后一次转换），证据 `test_renderer_adapter_compat.py` |
| K13 | local image standalone（data URI；失败保留原引用；`data:`、`file:`、原始 HTML 资源的既有策略） | `test_image_embedding.py`（14 项） |
| K14 | **adapter contract（renderer → core）**：`headings` 保留顺序，并保留 `level`、`anchor`、`text`、`inline_html`、`toc_inline_html` 的语义；TOC 与 Viewer 只消费这套结果，编号识别只有一个来源。字段名与序列化形式可以迁移，但必须 producer、consumer、tests 同步改并在本文件登记 | `test_toc_heading_contract.py`（45 项）+ `test_markdown_anchor_contract.py` + Viewer NUM1/NUM2 |
| K15 | warning 通道（可读路径、不阻断转换） | `test_renderer_links.py`、`test_conversion_edge_cases.py` |
| K16 | standalone HTML 装配（自包含、标题转义、无 CDN）—— **v1 生产路径**；v2 装配路径与 closure 判定见 K24（Phase 5D） | `test_demo_generation.py`、`test_converter_integration.py` |
| K17 | Viewer / 索引页 / GUI 行为契约 | `tests/js` 层：viewer 22、index 9、GUI 9、selfcheck 5 |
| K18 | 运行时归属与可靠调用：打包物只使用内置 Node（不借 PATH）、渲染前冒烟自检。**进程粒度不是契约**（见 IMPLEMENTATION DETAIL） | `test_node_runtime.py`（5 项） |
| K19 | 覆盖语义：`overwrite=false` 跳过并保留原文件 | `test_conversion_edge_cases.py` |
| K20 | 发布门禁与产物校验 | `test_release_freeze.py`、`test_release_validation.py` |
| K21 | 按需载荷：有公式才携带 KaTeX 资产，无公式不携带（体积纪律）。**具体信封键名不是契约** | `test_renderer_katex_assets.py`、`test_converter_integration.py` |
| K22 | Mermaid runtime 按需（AGENTS §9）：只有文档真的含 Mermaid 时才携带 runtime；普通 Markdown 的 envelope 与 HTML 都不带。runtime 是 vendored 的正式 browser 构建（与 npm 包内 `dist/mermaid.min.js` 逐字节相同），build 与运行期各校验一次 SHA-256，且**离线可渲染**（零网络请求） | `tests/test_renderer_adapter_mermaid_runtime.py`（19 项）+ `tests/browser`（opt-in，5 项，真实浏览器） |
| K23 | 远程资源（remote Markdown 图片 / PlantUML 图像）行为契约：联网成功 → data URI（`ref` 仍是作者原 URL，`resolved` 记最终 URL）；失败（超时 / 网络 / HTTP / 非图片 / 超限）→ **保留作者原引用 + 可读 warning + 转换继续**；同一 URL 的同一失败只报一次；`fetch_remote_resources=false` → kept 且不 warning；raw HTML 里的远程引用永不抓取。**timeout / retry / max-size / 并发数的数值是实现策略，不是契约**，但「数值越界一律回落默认值」与「body 读取阶段按 fetch 阶段同一规则分类、只有超限不 retry」属实现承诺（见 `renderer/resources/http_client.js`） | `tests/test_renderer_network.py`（26 项，127.0.0.1 loopback）+ `renderer/test/http_client.test.js`（26）+ `renderer/test/remote_resolver.test.js`（11） |
| K24 | **standalone closure verdict（Phase 5D，只针对 v2 装配路径）**：`standalone`（没有外部 subresource）/ `degraded`（资源层本该闭包的抓取或内嵌失败、保留原引用，且有 manifest + 可读 warning 证据）/ `author_references`（作者显式 raw HTML 的外部引用：**声明且被 renderer fragment 佐证**，既非 fallback 也非失败）/ `failure`（应闭包却既无 fallback 证据、也非 author-owned）；severity `failure > degraded > author_references > standalone`，报告**同时保留四个桶**并附 per-ref occurrence 账本。只判定真正的 subresource（`img[src]`/`srcset`、`script[src]`、`link[href]`、`<style>` 与 `style="…"` 属性内的 `url(...)`、`<style>` 内的字符串 `@import`）；`<a href>` 导航不参与；`<link>` 按 `rel` 优先级判定：出现 fetching token（stylesheet / icon / preload / modulepreload / prefetch / manifest / apple-touch-icon / mask-icon 等）即为 subresource，且 **fetching token 压过 metadata token**（`alternate stylesheet`、`author stylesheet` 仍算），只有全部为明确 metadata token（canonical / alternate / author / dns-prefetch / preconnect 等）才忽略，**未知 / 缺失 / 混合未知一律按 subresource**；`srcset` 按规范解析（不按逗号 split —— data URI 里的逗号是 URL 的一部分）。证据按 **occurrence** 消费：`最终外链数 = degraded（kept，或 failed 且有提及该 ref 的 warning）+ author（声明且被 fragment 佐证）+ unexplained`，**degraded 先占位**，因此 author 声明既不能把降级降级成 author，也不能吸收多余的 occurrence；声明的 occurrence 数超过 fragment 中真实次数同样判 `failure` | `tests/test_standalone_closure.py`（37 项，判定语义 + CLI）+ `tests/test_standalone_matrix.py`（22 项，真实 adapter + assembler + loopback + smoke 生成器）+ `tools/standalone_closure.py` |
| K25 | **author provenance 通道（Cutover C1，v2 additive）**：`resources.author_references = [{"ref": …, "count": n}, …]` —— 作者**自己写进文档的 raw HTML** 的外部 subresource 引用：每 ref 一条、`count >= 1`、顺序为首次出现顺序、普通文档为 `[]`。**必须在 token 层记录**（`html_block` / `html_inline`，parse 后、render 前）：一旦从最终 html 反推，raw HTML 与 Markdown 生成的 html 就无法区分，K24 的四态模型会退化。**只记录来源**：不 fetch、不改 html、不进 `resources.items`（K13 边界不扩大），协议仍 v2（additive 通道，`scripts` 同理）。参考集合与判定与 K24 的 checker 同构：`img[src]`/`srcset`、`script[src]`、`link[href]`（rel 为 fetching 或未知）、`<style>` 与 `style="…"` 内的 `url(...)`、`<style>` 内的字符串 `@import`；`<a href>` 与 `data:` / `about:` / `#` / 空引用不算；**HTML 注释与 `<script>` 内容不扫**（注释 HTMLParser 不看、脚本内容是 CDATA），否则会声明一个最终 html 里不存在的引用。checker 侧 `scan()` 在未显式给出 `--author-refs` 时**自动消费**该通道，且佐证计数与 ref 抽取走同一路径（不再裸子串计数，`&amp;` 这类字符引用也能对上） | `tests/test_renderer_author_references.py`（27 项：两侧共用 fixture + 端到端 verdict）+ `renderer/test/author_references.test.js`（24 项）+ `tests/fixtures/author_references.json`（node / pytest 共用） |

## TRANSITIONAL：记录现状，路线图已定要改

| # | 今天的真实行为 | 何时改 | 涉及测试 → 处理约定 |
| --- | --- | --- | --- |
| T1 | remote image **永远**保留原 URL | **Phase 5C 已改写**：默认联网尝试内嵌（成功 → data URI；失败 → 原 URL + warning + 转换继续）；`fetch_remote_resources=false` 时保留旧行为 | old production 侧 `test_image_embedding.py::test_remote_image_is_left_untouched` 继续锁旧 renderer；adapter 侧改为 `test_renderer_adapter_resources.py::test_remote_image_is_kept_when_fetching_is_disabled`，联网语义见 `tests/test_renderer_network.py` |
| T2 | 单一 `template` 选择、`extends` 继承链、`theme-<id>` body class | Phase 6–8：Theme registry、三个 builtin 常驻、`external_themes` | `test_demo_generation.py`、`test_template_style_contract.py` |
| T3 | `config.json` 的 `build.template`，配置与日志位于 EXE 同级 | Phase 8 / Phase 10：`external_themes` + `profile/` | 配置 schema 与 `test_gui_state_contract.py` |
| T4 | `samples/demo.html` 必须等于当前源码的输出 | Phase 4/6 输出必然变化：重新生成并在提交说明里解释 | `test_demo_generation.py::test_demo_html_matches_the_committed_specimen` |
| T5 | 标题 slug 的**精确值**（今天由 `slugifyUnicode` 给出） | Phase 4：允许按 vscode-office / markdown-it-anchor 对齐 | **不作断言**；诊断记录见下表 |
| T6 | Python TOC → Viewer 的 DOM contract：`data-explicit-number`（Viewer 据此标记“已编号”标题） | Phase 6：可以重新设计，但必须同步修改 producer（core/toc.py）、consumer（templates/viewer.js）与相关测试，并在本表登记 | Viewer NUM1/NUM2、`test_toc_heading_contract.py` |
| T7 | KaTeX 资产以单个 `assets.css` 全量内联 | **Phase 5A 已改**：adapter v2 用 `resources.styles` + `resources.items`（通用 CSS `url()` resolver）；旧 production renderer 仍是 `assets.css` | 断言只锁“有公式才有载荷、离线可用”；adapter 侧见 `tests/test_renderer_adapter_resources.py` |

### T5 诊断记录（当前输出，仅供对照）

锚点语料在 2026-09-24 的输出：`中文标题`、`带标点的标题`（标点被剥离）、`emoji-标题`（emoji 变分隔符）、重复标题后缀为 `2`、空标题为 `_1`、`A` → `a`。
这些值**不是契约**：Phase 4 允许改变，只要 K1 的关系成立。

## TARGET：本次升级新增（Phase 1 迁移门禁）

| # | case | Phase 1 断言（今天必须失败） | 完成的 Phase |
| --- | --- | --- | --- |
| G1 | checkbox | `type="checkbox"` 恰好 2 个，字面 `[ ] 未完成事项` 消失 | **Phase 4A 已在 adapter 实现**（`markdown-it-checkbox`，见 `tests/test_renderer_adapter_targets.py`）；旧 production renderer 仍 xfail |
| G2 | mark | 出现 `<mark>`，字面 `==高亮文本==` 消失 | **Phase 4A 已在 adapter 实现**（`markdown-it-mark`） |
| G3 | callout | `[!NOTE]` 与 `[!WARNING]` 都消失、正文保留；已收窄到 pinned 上游输出 `class="callout"` + `data-callout="note|warning"` | **Phase 4A 已在 adapter 实现**（`markdown-it-obsidian-callouts`） |
| G4 | wikilink | 字面 `[[` 消失；parser/alias 仍来自 pinned 上游，adapter 只把编辑器用的 `href="#"` 换成静态 export href。可见文本「第二章」「别名显示」，两个 href 非空且 decode 后识别目标「第二章」 | **Phase 4A 已在 adapter 实现**（`renderer/extensions/obsidian_wikilink_export.js`）；**Phase 4B 已接入 document_map**：源文件同目录下唯一的 `.md` / `.markdown` 目标 → 对应 `.html`（可带 fragment），解析不出唯一目标时保留 Phase 4A 的 fragment fallback，且不新增 warning |
| G5 | obsidian-tag | ASCII 与 Unicode 标签（`#note`/`#项目/子项`）都成 tag；`# 标题`/URL fragment/孤立 `#` 不误报 | **Phase 4A 已在 adapter 实现**（上游 obsidian token + MarkdownReader Unicode 字符集扩展） |
| G6 | mermaid | `features.mermaid` 为真，且出现 `class="mermaid"` 运行时容器 | **Phase 4C 已实现语义层**（`renderer/extensions/mermaid_export.js`：复刻 pinned 上游 recognition + 容器，内容按 D2 escape）；**Phase 5B 已交付 runtime**：vendored `mermaid@11.15.0` 经 `resources.scripts` 按需交付（K22），离线渲染由浏览器验收证明；standalone 终检仍属 5D |
| G7 | plantuml | `features.plantuml` 为真，且进入图像资源流程（出现 `<img`） | **Phase 4C 已实现语义层**（`markdown-it-plantuml@1.4.1`：`uml_diagram` token + `<img src="server/svg/…">`，只构造 URL）；**Phase 5C 已接入抓图**：成功 → `data:image/svg+xml;base64,…`（`resolved` = 最终 URL），失败 → 保留 server URL + warning + 转换继续，feature 不变（K23，`tests/test_renderer_network.py`） |

**Phase 4C 的 PlantUML 形式记录**：pinned 上游的**导出**路径（`markdown-pdf.js` → `markdown-it-plantuml`）只识别**裸 `@startuml` 块**；以围栏代码块（语言标记 `plantuml`）写图表只存在于 vditor 编辑器子系统，不属于导出语义。Phase 1 语料 `target/plantuml.md` 用的是围栏形式，因此 Phase 4C 增加了一条明确的 **adapter 附加**：语言标记为 `plantuml` / `puml` 的围栏会转成同一个 `uml_diagram` token（围栏 body 视为作者写的完整图源，原样编码，不删标记也不重新包装）。两条路径共用同一个 URL 构造实现，`<img>` 渲染与 feature 判断仍只有插件一个来源。**契约边界**：围栏契约只覆盖 『body 内含 `@startuml` / `@enduml`』的写法；不定义缺失标记时自动补齐（未来若要支持，须作为独立产品能力自带 fixture 与 contract）。

**Phase 5A 的协议记录（v2）**：adapter 的成功 envelope 升到 `protocol_version = 2`，新增**必在**字段 `resources` —— `items` 是资源 manifest（`{ kind, source, ref, status }`，内嵌时另有 `mime` / `resolved`），`styles` 是交给 assembler 注入的 CSS（目前只有 `katex`）—— 5B 追加了 `scripts`（按需交付的脚本，今天只有 `mermaid`，属 v2 的 additive 通道）。协议版本描述 wire schema，不表示哪个 renderer 已成为 production；v1 的 `assets.css` 只属于旧 production renderer。`warnings` 仍是**用户可读字符串数组**：成功内嵌不产生 warning（状态记在 manifest），只有降级、缺失、不可读等需要作者注意的情况才进入 warnings。资源层边界：只处理 **Markdown image token** 与**明确交给资源层的 CSS**；raw HTML 里的图片标签与 `style` 属性里的 `url(...)` 一律不参与内嵌（K13 边界不得扩大）。KaTeX 的样式与字体由 `npm run build` 复制到 `dist/katex/`（companion runtime asset），运行期不依赖 `renderer/node_modules`；通用 CSS `url()` resolver（`renderer/resources/css_resolver.js`）与 Theme 无关，Phase 6/7 直接复用。远程抓取（T1）与 PlantUML 抓图（G7 的资源部分）自 Phase 5C 起实现（K23）；Mermaid runtime 自 5B 起按需交付（K22）。
Phase 1 **只锁产品级语义，不锁尚未 pin 住的上游 DOM**。Callout 与 Obsidian tag 先接受一个允许集合（`callout`/`admonition`/`markdown-alert`/`alert`/`note`；tag 类名或 `tag` 链接）；Phase 2 固定 vscode-office commit、Phase 3 adapter 定型之后，再补确实需要的上游 DOM contract。

## IMPLEMENTATION DETAIL：允许重构

`render.js` 的文件布局与内部函数名（`installHeadingIds`、`slugifyUnicode`、`resolveImageSource`、`rewriteDocumentHref`、`decodeForDisplay`…）、旧 renderer 的 `assets.css` 键名（v2 的 `resources` 形状才是契约，见 Phase 5A 协议记录）、`warnings` 文案（除“路径可读”这一产品要求）、CSS/JS 注入位置、`linkify.set()` 的调用形式、`templates/Modern` 目录名与 id `modern` 的大小写依赖、`_theme_body_class` 的具体类名、每文档一个 Node 进程。

本清单只包含拼写、序列化与组织方式；它们的**语义**属于 KEEP（`headings` 通道见 K14、运行时归属见 K18、KaTeX 载荷见 K21）。进程粒度只在这里出现一次。

## 迁移 fixture 语料

```text
tests/fixtures/markdown/
├─ manifest.json                 索引：schema / groups / cases[{id, group, file, note}]
├─ keep/*.md                     15：必须保持的语法
├─ target/*.md                    7：要新增的语法
└─ anchor/anchor-relationship.md  1：锚点关系语料
tests/markdown_fixtures.py       只负责读取与渲染，不构造测试 DSL
```

manifest 只是索引：schema 版本、case id、分组、fixture 路径、简短说明。断言全部写在 Python 测试里，新增第五个字段需要在 `AGENTS.md` 允许的范围内说明理由。

| case | 分组 | 文件 | 证明它的测试 |
| --- | --- | --- | --- |
| inline-basic | keep | keep/inline-basic.md | `test_markdown_compat_keep.py` |
| paragraph-breaks-off | keep | keep/paragraph-breaks-off.md | 同上 |
| typographer-off | keep | keep/typographer-off.md | 同上 |
| heading-levels | keep | keep/heading-levels.md | 同上 |
| heading-trailing-hash | keep | keep/heading-trailing-hash.md | 同上 |
| code-fence-heading-text | keep | keep/code-fence-heading-text.md | 同上 |
| table-alignment | keep | keep/table-alignment.md | 同上 |
| code-fence-language | keep | keep/code-fence-language.md | 同上 |
| blockquote-and-hr | keep | keep/blockquote-and-hr.md | 同上 |
| list-nested | keep | keep/list-nested.md | 同上 |
| raw-inline-html | keep | keep/raw-inline-html.md | 同上 |
| link-and-autolink | keep | keep/link-and-autolink.md | 同上 |
| footnote | keep | keep/footnote.md | 同上 |
| math-inline-display | keep | keep/math-inline-display.md | 同上 |
| plain-text-no-math | keep | keep/plain-text-no-math.md | 同上 |
| checkbox | target | target/checkbox.md | `test_markdown_compat_target.py`（xfail） |
| mark | target | target/mark.md | 同上 |
| callout | target | target/callout.md | 同上 |
| wikilink | target | target/wikilink.md | 同上 |
| obsidian-tag | target | target/obsidian-tag.md | 同上 |
| mermaid | target | target/mermaid.md | 同上 |
| plantuml | target | target/plantuml.md | 同上 |
| anchor-relationship | anchor | anchor/anchor-relationship.md | `test_markdown_anchor_contract.py` |

语料只补“今天仅由 demo 快照隐式覆盖”的语法。本地图片、跨文档 `.md` 链接与 Front Matter 已有专门模块（K10–K13），这里不重复造语料。

## 已知迁移差异

差异分三类处理：**expected**（路线图已预计）／**harmless**（实现差异，用户看不出）／**regression**（真实产品回退）。只有 regression 会阻断 closeout；登记在此的差异都是**有决策的**，不是测试遗漏。

| # | 差异 | 旧 production（texmath） | pinned upstream | 决策 |
| --- | --- | --- | --- | --- |
| D1 | 行内 `$` 的空白保护 | `dollars` 规则要求 `$…$` 内容不以空白结尾，因此「价格 $100 与 $200 之间。」不是公式 | `math_inline` 只跳过转义 `$` 与空的 `$$`，同一句会被配成公式 | **ACCEPTED UPSTREAM DIFFERENCE** |
| D2 | Mermaid 容器内容 | 不适用（旧 renderer 无 Mermaid） | 未转义插值：`<div class="mermaid">${code}</div>` | **INTENTIONAL EXPORT HARDENING** |

**D1 决策理由**（Phase 4A+4B closeout 明确接受，不修改）：

- `$…$` / `$$…$$` 的 ownership 已归 pinned vscode-office；
- 不在 MarkdownReader 内创建第二套 dollar parser，也不加 before-rule guard 去重新解释 `$`；
- 后续如需改变，应优先通过 upstream issue / contribution / upstream commit 更新解决。

行为由 `tests/test_renderer_adapter_compat.py::test_a_dollar_pair_across_prose_is_a_recorded_upstream_difference` 锁定（**不得**改回「旧行为必须保持」），并由 `tests/test_renderer_semantic_parity.py::test_accepted_dollar_pair_difference_is_explicit` 同时锁定「它已被登记」。

KEEP 契约未受影响：`keep/plain-text-no-math` 用的是单个未配对 `$` 与转义 `\$`，adapter 上仍然不产生公式（该 case 由 `test_renderer_adapter_keep.py` 覆盖）。

**D2 不变式**（与 D1 不同类：它不是语义差异，而是有意的输出加固）：upstream 把 Mermaid source 未转义地插入容器 HTML；MarkdownReader 在 serialization 时 HTML-escape，使其在 runtime 处理之前保持惰性文档文本。**Required invariant**：交给 Mermaid 的 DOM 文本表示必须能 round-trip 回原始图源（证据：`test_mermaid_container_escapes_but_round_trips_the_author_source` 与 `test_mermaid_container_preserves_author_entities` —— 作者写 `&amp;` 时上游会被浏览器先解码，本 adapter 保持作者原文）。

除 D1、D2 之外，本次 closeout 未发现其它 old/new 语义差异：math 能力矩阵的其余 16 个样本（含全部负例）两边一致（`test_math_capability_matrix_matches_except_the_accepted_difference`）。

## Phase 4A+4B Semantic Parity Closeout（2026-09-24）

在进入 Mermaid / PlantUML 之前建立的一层 **old production renderer ↔ new adapter** 语义对照证据（`tests/test_renderer_semantic_parity.py`）。比较的是**产品级语义**，不是 HTML 字节：不比较属性顺序、空白、heading slug 精确值、upstream class 细节、KaTeX MathML 字节、token 顺序。

| 场景 | 证据 | 结果 |
| --- | --- | --- |
| A 基础 Markdown | `test_basic_markdown_semantics_match` | strong / em / strike / inline code / 转义 / 软换行 / 嵌套列表 / 表格对齐 / 围栏语言 / 引用 / raw HTML 共 13 项语义标记两侧一致 |
| B heading relationship（K1） | `test_heading_relationship_holds_in_both_renderers` | 两边 id 非空唯一、与各自正文 id 对应；(level, text) 一致；anchor **文本**不作比较（T5） |
| C linkify | `test_linkify_contract_holds_in_both_renderers` | 真实 URL 仍可点；裸文件名与版本号不被 fuzzy linkify |
| D footnote（K8） | `test_footnote_structure_matches` | ref / 脚注区块 / backref / 字面消失 两侧一致（不锁编号字符串） |
| E document link（K12） | `test_document_link_href_parity`、`test_unlisted_target_warning_parity` | 5 类输入 href 完全一致；warning 数量·类别·可读路径一致；heading 内链接只警告一次 |
| F footnote + document link | `test_footnote_with_document_link_matches` | 脚注定义内链接被改写、fragment 保留、warning 为 0 |
| G math | `test_math_capability_matrix_matches_except_the_accepted_difference` | 16 个样本（`$`、`$$`、`\(\)`、`\[\]`、`equation`、`align` 与全部负例）一致；唯一差异是 D1 |
| H/I/J 注册表与范围 | `test_migrated_and_pending_registries_are_locked`、`test_features_are_adapter_only`、`test_resource_layer_channel_differs_by_design_after_phase5a` | KEEP 15/15、Phase 4A 五项已迁移、Mermaid / PlantUML 仍 pending、features 只属 adapter、资源交付通道 old/new 形状不同（Phase 5A 登记，不做 equality） |

比较范围之外：local image data URI 与 KaTeX CSS/fonts 载荷（**Phase 5A 已在 adapter 侧完成**，但通道形状与 old 的 `assets.css` 不同，仍不做 equality）、remote image 与抓取、Mermaid runtime、PlantUML 图像、standalone 资源闭包（属 5B/5C）。

当前数字（按套件）：`test_renderer_semantic_parity.py` 12、`test_renderer_adapter_keep.py` 20、`test_renderer_adapter_targets.py` 14（4A 条目里的 13 项是那次提交当时的计数）、`test_renderer_adapter_compat.py` 35、`test_renderer_adapter_diagrams.py` 27、`test_renderer_adapter_protocol.py` 11、`test_renderer_adapter_resources.py` 26（Phase 5A）、`test_renderer_adapter_mermaid_runtime.py` 19 与 `test_renderer_build_assets.py` 3（Phase 5B）、`test_renderer_network.py` 26（Phase 5C，127.0.0.1 loopback）、`test_standalone_closure.py` 37 与 `test_standalone_matrix.py` 22（Phase 5D）。

全套：`uv run pytest -q` → 362 passed, 7 xfailed；renderer `npm test` → 61 passed；浏览器验收（opt-in）`pwsh tools/run_browser_acceptance.ps1` → 5 passed（默认 pytest 不含它）；`uv run pytest -q --runxfail tests/test_markdown_compat_target.py` → `7 failed, 2 passed`（TARGET 门禁仍是 strict xfail）；`uv run ruff check .` → All checks passed。

## AGENTS §25 必测项覆盖映射

| 要求 | 证据 |
| --- | --- |
| Markdown 基础语法 | keep 语料（K2–K7） |
| checkbox / mark / Callout / WikiLink | TARGET G1–G4（xfail，Phase 4） |
| footnote | K8 |
| footnote / 额外数学分隔符 / 文档链接（adapter 侧） | Phase 4B：`tests/test_renderer_adapter_compat.py`（35 项） |
| KEEP 语料在 adapter 上的对照 | `tests/test_renderer_adapter_keep.py`（20 项，15/15 KEEP case 全覆盖，footnote 于 Phase 4B 补齐） |
| Mermaid / PlantUML（adapter 侧） | Phase 4C：`tests/test_renderer_adapter_diagrams.py`（27 项）+ `renderer/test/mermaid_predicate.test.js`（node:test）；Phase 5B：`tests/test_renderer_adapter_mermaid_runtime.py`（19 项）+ `tests/browser`（opt-in 5 项，真实浏览器离线渲染）；Phase 5C：PlantUML 抓图见 `tests/test_renderer_network.py` |
| KaTeX | K9 |
| Mermaid / PlantUML | TARGET G6–G7（旧 production 仍 7 strict xfail）；adapter 侧 Phase 4C：`tests/test_renderer_adapter_diagrams.py`（27 项） |
| local image / remote image | K13（remote 同时登记为 T1，Phase 5C 已改写）；adapter 侧 Phase 5A：`tests/test_renderer_adapter_resources.py`（26 项）；联网语义 Phase 5C：`tests/test_renderer_network.py`（26 项，127.0.0.1 loopback） |
| `.md → .html` | K12 |
| Front Matter | K10 |
| heading anchor | K1 |
| TOC | K14 |
| 三个 builtin themes | T2 现状；Phase 6 起由 `tests/js` 与 `test_demo_generation.py` 承担 |
| external theme / HTML theme switching | Phase 6–7（今天不存在） |
| dark/light | `tests/js/viewer.test.js` |
| Viewer state | `tests/js/viewer.test.js`（22 条） |
| 中文路径 / 含空格路径 | `test_renderer_links.py`、`test_conversion_plan.py`、`test_image_embedding.py` |
| 无网络 fallback | 今天语义不存在（T1），Phase 5 建立 |
| onedir / onefile | 不在 pytest 范围：`packaging/*` 与人工验收清单（见 DEVELOPMENT.md） |

## TARGET 门禁规则

1. 每条 TARGET case 今天都必须真实执行并失败（`xfail(strict=True)`），不得用 skip 伪装。
2. 上游接入后一旦通过，pytest 会把 XPASS 报成失败：必须把该 case 正式改成 `pass`。
3. Final Acceptance 之前不允许遗留 `xfail`、为发布 skip 掉的失败测试或注释掉的断言。
4. 反证命令：`uv run pytest -q --runxfail tests/test_markdown_compat_target.py`，期望 `7 failed, 2 passed`（2 条是登记检查与健全性检查）。

## 当前实测数字（2026-09-24，Phase 1）

```text
uv run pytest -q                         → 157 passed, 7 xfailed（164 项）
新增测试                                  → keep 16 + anchor 8 + target 9 = 33 项
JS 层                                     → viewer 22 / index 9 / GUI 9 / selfcheck 5，全部 pass
node_renderer: npm test                   → PASS（node --check render.js）
samples/demo.html                         → 未改动，快照契约仍成立
```

## Backlog（本阶段只记录，不修）

1. `core/config.py`：`features.overwrite` 只读不写，设置无法持久化。
2. `templates/Modern` 目录名与 id `modern` 的差异依赖 Windows 大小写不敏感文件系统。
3. `docs/ROADMAP.md`（Theme System v2 / 模板）与 `docs/REFACTOR_ROADMAP.md`（Theme / 主题）词汇冲突，需要统一口径。
4. `packaging/node/` 不入库，本机无法构建发布物（spec 会显式失败）。
5. `AGENTS.md` §24 要求 `core/paths.py`，今天路径判定仍在 `core/config.py`。
6. 裸邮箱 `qa@example.com` 不被 linkify，与 `fuzzyLink:false` 相邻但未在 `MARKDOWN.md` 说明；本轮刻意不写成契约。
7. `docs/DEVELOPMENT.md` 的 `cd tests/js; npm test` 直接运行会因缺 `MR_VIEWER_JS` 失败（该变量由 pytest wrapper 注入，pytest 路径正常）；命令说明需要修正，本轮只记录不修。

## 变更记录

- 2026-09-24（Phase 1）：建立迁移语料、KEEP/TARGET 两组契约、锚点关系契约与本页；Phase 0 基线记录写入 [重构路线图](REFACTOR_ROADMAP.md)。
- 2026-09-24（Phase 4A）：新 renderer adapter 接入 **checkbox / mark / Callout / WikiLink / Obsidian tag**（G1–G5）：
  parser/token 仍全部来自 pinned vscode-office 与上游所用插件；WikiLink 增加薄静态 href 适配（`renderer/extensions/obsidian_wikilink_export.js`）；
  Obsidian tag 增加**最小** Unicode 字符集兼容扩展（`renderer/extensions/obsidian_tag_unicode.js`：上游 pinned 只认 ASCII）；
  features 五项改由 **token 语义**驱动，raw HTML 不再误报；mermaid / plantuml 仍 pending。
  证据：`tests/test_renderer_adapter_targets.py`（13 项）+ `tests/test_renderer_adapter_keep.py`（19 项）；旧 production TARGET 门禁仍 7 strict xfail。
- 2026-09-24（Phase 4B）：新 renderer adapter 接入 **footnote / 额外数学分隔符 / 文档链接**：
  * footnote 由 MarkdownReader-owned `markdown-it-footnote@^4.0.0` 承担（pinned 上游没有实现）：KEEP 语料补齐到 15/15，`test_renderer_adapter_keep.py` 的 `PENDING_CASES` 清空；
  * `\(…\)`、`\[…\]`、`\begin{env}…\end{env}` 由 `renderer/extensions/math_compat.js` 解析，**只 push 上游的 `math_inline` / `math_block` token**，渲染仍由 pinned 上游 KaTeX renderer 完成。**不引入 `markdown-it-texmath`**：它按硬编码规则名注册并覆盖同一个 `renderer.rules` 键，会连带接管 `$` 的渲染（所有权反转），审计记录见下；
  * `.md` / `.markdown` 文档链接与 WikiLink 目标解析进入 document 层 `renderer/document/links.js`（parse 后、render 前只跑一次，heading 内的链接 warning 因此不再重复），并删除 Phase 3 的 `context.document_map` deferred warning；
  * `features.katex` 改为 token 驱动（真实数学 token **且** 确实产生 KaTeX markup），raw HTML lookalike 不再误报；
  * 语法与旧 renderer 的差异由 characterization 决定并锁定：`align*`、大写 env、不配对 env、段中 `\[`、跨行 `\(`、4 空格缩进都不构成公式；
  * 新发现的上游差异记入「已知差异」D1（不修，需 §6 决策）。
  证据：`tests/test_renderer_adapter_compat.py`（35 项）+ `tests/test_renderer_adapter_keep.py`（20 项）；全套 `uv run pytest -q` → `254 passed, 7 xfailed`；renderer `npm test` → 6 passed；旧 production TARGET 门禁仍 7 strict xfail。
- 2026-09-24（Phase 4A+4B Semantic Parity Closeout）：建立 old production renderer ↔ new adapter 的语义对照层（`tests/test_renderer_semantic_parity.py`，12 项，比较产品级语义而非 HTML 字节）：
  * 基础 Markdown（13 项标记）、heading relationship、linkify、footnote、document link（5 类 href + warning 数量·类别·可读路径）、footnote+link 联合场景，两类 renderer 逐项一致；
  * math 能力矩阵 16 个样本（`$`、`$$`、`\(\)`、`\[\]`、`equation`、`align` 与全部负例）两侧一致，**唯一差异是 D1**；
  * D1 正式登记为 **ACCEPTED UPSTREAM DIFFERENCE**（理由与「不修改」的边界见上一节）；
  * KEEP 15/15、Phase 4A 五项已迁移、Mermaid / PlantUML 仍 pending、features 只属 adapter、资源层 Phase 5 pending，由注册表断言锁定；
  * 纯文档修正：`docs/MARKDOWN.md` 补上已 characterization 的 begin/end 数学环境（小写环境名、`\begin`/`\end` 同名）；
  * 未切换 production、未迁移任何资源层代码、未新增 protocol 字段。
  证据：`uv run pytest -q` → `266 passed, 7 xfailed`；renderer `npm test` → 6 passed；`--runxfail` 反证仍 `7 failed, 2 passed`。

- 2026-09-24（Phase 4C）：新 renderer adapter 接入 **Mermaid recognition/容器** 与 **PlantUML 语义层**：
  * Mermaid：**不引入 `mermaid` 依赖**，只复刻 pinned 上游的 recognition predicate（exact `mermaid`、首行 `gantt` / `sequenceDiagram` / `graph TB|BT|RL|LR|TD`（可带 `;`），且**不看围栏语言**）与容器 HTML。
    实测证据：mermaid 11 的 `parse()` 是 Promise（非法输入 reject `UnknownDiagramError`；未捕获时 node **exit 1**），上游的同步 try/catch 捕获不到，且打包上游插件 + mermaid 会让 renderer.cjs 从 1,063,499 B 涨到 **7,170,453 B / 1929 modules**。语法校验与浏览器 runtime 全部留给 Phase 5（G6 的 runtime 部分仍 pending）。
  * PlantUML：新增 `markdown-it-plantuml@^1.4.1`（lockfile 精确版本 1.4.1，与 pinned 上游声明一致；无 runtime 依赖，只生成 server URL）。`uml_diagram` token 与 `<img>` 渲染都归插件；URL 构造集中在一个实现，通过插件的 `generateSource` 使用；server 由 `options.plantuml_server` 配置并有默认值。**不做任何网络访问**（抓图与内嵌属 Phase 5，G7 的资源部分仍 pending）。
  * 发现的差异（已登记）：pinned 上游导出路径只识别**裸 `@startuml` 块**，而 Phase 1 语料用的是围栏形式 → Phase 4C 增加明确的 adapter 附加（`plantuml` / `puml` 围栏 → 同一个 `uml_diagram` token）。
  * D2（新增）：Mermaid 容器内容在 serialization 时 escape，登记为 **INTENTIONAL EXPORT HARDENING**，不变式是「DOM 文本 == 作者原文」。
  * features：mermaid 由 fence token 的语义标记驱动，plantuml 由 `uml_diagram` token 驱动；两项的 raw HTML lookalike 都不误报。
  * **Phase 4C — PASS**（用户确认）：PlantUML 围栏附加保留为 adapter extension，不改 Phase 1 fixture；D1 / D2 分类维持不变。commit `0eeaf1a`。
  证据：`tests/test_renderer_adapter_diagrams.py`（27 项）+ `tests/test_renderer_adapter_targets.py`（14 项，MIGRATED 7 / PENDING 0）+ `renderer/test/mermaid_predicate.test.js`（node:test，合计 9 项）；bundle 1,063,499 → 1,107,699 B；全套 `293 passed, 7 xfailed`。

- 2026-09-24（Phase 5A）：adapter 资源层落地（**仅静态资源，不联网**）：
  * **协议升到 v2**：成功 envelope 新增**必在**字段 `resources`（`items` manifest + `styles` 待注入 CSS）。不采用「v1 + 可选 resources」：版本号描述 wire schema，而不是哪个 renderer 已成为 production；v1 的 `assets.css` 只留在旧 production renderer 的历史测试与文档里。
  * **Markdown 本地图片**：`renderer/resources/local_file.js`（唯一的 data URI 实现）+ `renderer/resources/collector.js`（parse 后、render 前只处理 image token）。K13 的既有语义逐条重放：相对路径、Windows 绝对路径（`C:/…`，判断顺序必须先于通用 scheme）、中文与空格路径、重复引用、链接内图片、TOC 侧仍只留 alt 文本、`data:` 与远程与其它 scheme 不碰、读不到时保留原引用 + 可读路径 warning、源文件与源图片不被修改。
  * **不得扩大的边界**：raw HTML 里的图片标签与 `style` 属性里的 `url(...)` **不参与**内嵌 —— collector 只看 token，不扫描最终 HTML；专门测试锁定「同一文件的 raw 写法与 Markdown 写法结果不同」。
  * **通用 CSS `url()` resolver**（`renderer/resources/css_resolver.js`）：输入 CSS + base directory，输出内联后的 CSS 与 manifest；外部 URL、fragment、`data:` 与其它 scheme 原样保留，读不到则保留引用并报可读路径。本阶段只接到 KaTeX，**不建 Theme Registry**；Phase 6/7 的 theme CSS 复用同一模块。
  * **KaTeX 自包含 build artifact**：`npm run build` 把 `node_modules/katex/dist` 的样式与它引用的字体复制到 `dist/katex/`（只读、不联网），运行期只用该目录，**不依赖 `renderer/node_modules`**；有测试把 `renderer.cjs` + `katex/` 拷到临时目录（旁边没有 node_modules）运行并断言字体仍内嵌。K21 载荷纪律不变：无数学 token 时 `resources.styles` 为空。
  * warnings 仍是**用户可读字符串数组**：成功内嵌不产生 warning（状态记在 manifest），`resource-*` 之类的成功提示被明确排除，K15 不被无意义改写。
  * 明说未做的事：HTTP、remote image、PlantUML 抓图、Mermaid runtime、Theme Registry、standalone 终检、production renderer 切换（分别留给 5B / 5C 与后续阶段）。
  证据：`tests/test_renderer_adapter_resources.py`（26 项，新增）+ `renderer/test/css_resolver.test.js`（node:test 5 项）+ `renderer/test/protocol.test.js`（v2 断言）；全套 `319 passed, 7 xfailed`；renderer `npm test` 15 passed；bundle 1,107,699 → 1,118,095 B，companion asset 61 文件 / 1,100,399 B；`--runxfail` 反证仍 `7 failed, 2 passed`。

- 2026-09-24（Phase 5B）：Mermaid runtime 落地（**按需交付 + vendored + 可实证离线**）：
  * **vendored 正式 browser 构建**：`renderer/vendor/mermaid/11.15.0/`（`mermaid.min.js` 3,312,967 B + MIT LICENSE + metadata.json），与 npm 包内 `dist/mermaid.min.js` **逐字节相同**（SHA-256 `70137e77…65de`，tarball sha1 `b485c13e…`）。选 11.15.0 是因为 pinned 上游声明 `"mermaid": "^11.15.0"`。
  * **唯一联网入口**是 `tools/update_mermaid_runtime.ps1`（`npm pack` 精确版本 → 只提取产物与许可证 → 记录 SHA → 写 metadata）；普通 `npm run build` 只校验、不下载、不更新。
  * **v2 additive 通道**：`resources.scripts = [{ id, version, script, boot }]`，仍「必在」；`boot` 是 adapter-owned 的激活 wiring（`initialize({ startOnLoad: false })` 一次 + **每个容器各自** `run({ nodes: [node] })` 且各自 catch，同步抛也不中断 `forEach`）—— 因此单个图失败不阻断其它图、也不留未捕获 rejection。协议版本仍为 2。
  * **按需纪律（AGENTS §9）**：识别复用 4C 的唯一 predicate（`isMermaidFence`），因此 `features.mermaid` 与是否交付 runtime **逐样本一致**（含隐式首行 `gantt` / `sequenceDiagram` / `graph …`、`js` 语言围栏、空 fence、raw HTML 容器、PlantUML 文档）；普通 Markdown 的 envelope 与 HTML 都不带 runtime。
  * **构建改为 staged + verified + rollback-protected replacement**（回应用户对 5A 的两条记录）：`renderer.cjs` / `katex/` / `mermaid/` 全部先写进 `dist/.staging/` 并复验（存在性 + staging 内 runtime 的 SHA-256 == vendor），staging 无论成败都会清理；安装前把旧 assets 移到 `dist/.backup/`，全部成功即删除，**中途失败则回滚**到旧 managed set（rollback 自身失败时保留 `.backup/` 并报出路径，不假装恢复成功）。因此「构建/校验失败」发生在安装之前，正式 dist 完全不变，也不会残留旧版本字体文件。vendor 校验同样前置（metadata/产物/许可证/字节数任一不符即拒绝构建）。三个独立路径不构成文件系统级原子事务。
  * **运行期再校验一次** SHA-256；runtime 缺失或被改动时**降级而非失败**（warning + 不交付，容器与语义层照常）。
  * **浏览器验收（opt-in）**：`tests/browser`（playwright，`tools/run_browser_acceptance.ps1`，默认用系统 Edge 不下载浏览器）+ 人工 QA。它用真实 adapter 渲染 → 自装配页面 → 拦截所有非 `file://` 请求 → 断言容器内真的生成 `<svg>`，并单独锁定 D2 不变式（DOM 文本 == 作者原文）。默认 pytest 仍不依赖浏览器。
  * 明说未做的事：HTTP 抓取、remote image、PlantUML 抓图、Theme Registry、standalone 终检、production renderer 切换（仍属 5C/5D 与后续阶段）。
  证据：`tests/test_renderer_adapter_mermaid_runtime.py`（19 项，新增）+ `tests/test_renderer_build_assets.py`（3 项，新增，篡改/缺件必须拒绝构建且不触碰 dist）+ `renderer/test/build_assets.test.js`（node:test 16 项）；全套 `340 passed, 7 xfailed`；renderer `npm test` 25 passed；浏览器验收 4 passed（Edge、零网络请求、三类图表生成 SVG）；bundle 1,118,095 → 1,122,230 B（runtime 不进 bundle）。

- 2026-09-24（Phase 5B reliability closeout）：修两个「声明与实现不一致」的可靠性问题，**不新增功能、不进入 5C**：
  * **逐图故障隔离**（`renderer/resources/mermaid_runtime.js`）：`boot` 由「一次 `run` 全部节点」改为 `initialize` 一次 + `Array.from(querySelectorAll("div.mermaid"))` + **每节点** `run({ nodes: [node] })` + 各自 catch（同步抛也不中断 `forEach`）；`[node]` 形态在 mermaid 11.15.0 上先做了真实浏览器 characterization（无需特殊处理）。浏览器反证：**invalid 图在前、valid 图在后**的同页文档，后者仍生成 `<svg>`，且无未捕获 rejection、无 `pageerror`、网络请求仍为 0；坏图的最终 DOM 形态刻意不冻结。
  * **不再声称不存在的原子性**：`dist/.staging` 生命周期改为 `withStaging`（`try/finally`：esbuild / KaTeX 复制 / Mermaid 复制 / staging 复验任一步失败都清理 staging），安装改为 `publishManagedAssets`（旧 assets → `dist/.backup/` → 安装 staged assets → 成功清理 / 失败回滚，rollback 未完成则保留 `.backup/` 并报出路径）。代码注释、日志与文档统一改用 **staged + verified + rollback-protected replacement**。
  * **确定性反证**（node 层注入 fs-ops adapter，不依赖文件锁 / 磁盘空间 / 权限）：backup 移动失败、首次安装失败、部分安装后失败都恢复完整旧 set；rollback 自身失败时保留 `.backup/`；`withStaging` 成功与失败都不留 `.staging`；无关文件不受影响；stale 旧文件仍消失。
  证据：renderer `npm test` 25 → 32 passed；浏览器验收 4 → 5 passed（新增 mixed case）；全套 `340 → 341 passed, 7 xfailed`；`--runxfail` 仍 `7 failed, 2 passed`。

- 2026-09-24（Phase 5C）：远程资源联网内嵌（remote Markdown 图片 + PlantUML 图像），失败一律降级、不阻断转换：
  * **传输层**（新 `renderer/resources/http_client.js`）：只做 GET / timeout / retry / redirect / Content-Type 与大小校验，不做业务判断。策略（implementation policy）：timeout 8 s、retries 1、retry delay 固定 150 ms、单资源 16 MiB；retry 只在 network error / timeout / HTTP 5xx，4xx 与内容校验失败不 retry；Content-Length 超标立即拒绝（不读 body），无长度则读流累计超限即 abort；只接受 `image/*`（可带参数），**只有缺** Content-Type 才按 URL 扩展名回退；**不新增 npm 依赖**（Node 内置 fetch；缺 fetch 的运行时降级为可读失败）。
  * **解析层**（新 `renderer/resources/remote_resolver.js`）：conversion-scoped URL cache —— 同一 normalized URL 只创建**一个** Promise，重复引用即使并发也只请求一次，成功与失败都缓存；`runWithConcurrency` 并发上限 4 且结果按 job index 回写。
  * **collector classify-first**：所有 Markdown image token 先 classify，`data:` / remote 不再需要 `source_path`；local 无基准 → kept 且**不**报 warning（不引入 `unresolved`）；raw HTML 与 `style` 里的引用依旧完全不抓取；`uml_diagram` token 只消费 `attrs.src`（不重新解析 `@startuml`、不重新编码）。
  * **顺序与去重**（用户批准的 policy）：`resolved` 在远程成功时记 `response.url`（失败省略 `resolved`）、retry delay 150 ms、并发 4、manifest / warnings / HTML mutation 一律**文档顺序**、duplicate URL 只请求一次；同一 URL 的同一失败只产生一条 warning。
  * **降级语义**：任何失败（超时 / 网络 / HTTP / 非图片 / 超限 / 关网）都保留**作者原引用** + 可读 warning + 转换继续；protocol-relative 用 HTTPS 抓取但 fallback 仍是 `//host/x`；允许 http(s) 内重定向（`resolved` 记最终 URL），最终 URL 非 HTTP(S) 视为失败。
  * **T1 改写**：remote image 由「永远保留 URL」改为「默认联网内嵌；失败保留 URL + warning」；old production 的 `test_image_embedding.py::test_remote_image_is_left_untouched` 继续锁旧 renderer，adapter 侧改写为 `test_renderer_adapter_resources.py::test_remote_image_is_kept_when_fetching_is_disabled`。
  * **不访问公共互联网的 gate**：`tests/renderer_adapter.py::render()` 默认注入 `fetch_remote_resources=false`；真实联网语义只在 `tests/test_renderer_network.py` 用 127.0.0.1 loopback 服务器（`tests/loopback_http.py`）验证，其中一条**不传**该选项，因此同时证明生产默认 = 联网抓取。
  * 明说未做的事：CSS 远程 `url()`、theme assets（Phase 6/7）、磁盘 cache、magic-byte 嗅探、全局下载预算、GUI 选项、protocol 版本升级（仍 v2）、standalone 终检（5D）。
  证据：`tests/test_renderer_network.py`（21 项，端到端 + 环回）+ `renderer/test/http_client.test.js`（20）+ `renderer/test/remote_resolver.test.js`（11）；全套 `341 → 362 passed, 7 xfailed`；renderer `npm test` 32 → 61 passed；bundle 1,122,431 → 1,135,968 B。

- 2026-09-25（Phase 5C reliability closeout）：修两个「声明与实现不一致」的可靠性问题，**不新增功能、不进入 5D**：
  * **body 读取阶段的失败分类**（`renderer/resources/http_client.js`）：`fetch` 已返回头之后，`readLimited()` 里的 `reader.read()` 因 `AbortSignal.timeout` / socket 中断抛错时，原先被硬编码成 `network / 不 retry`，与已登记的「network error / timeout 可 retry」不一致（慢服务器完全可能走到这条路）。现在 fetch 阶段与 body 阶段**共用同一个分类器**，且只按 `error.name` 判别（`TooLargeError` → `too-large` 不 retry；`AbortError` / `TimeoutError` → `timeout` 可 retry；其它读错误 → `network` 可 retry），不再比对 `error.message`。每次 retry 都是**完整重新 GET**（新 `AbortSignal` + 新 `Response`），不复用已失败的 body reader。
  * **数值 option 的范围 gate**（同一文件）：`resource_timeout_ms` / `resource_retries` / `resource_max_bytes` 原先只校验 `Number.isFinite`，负数与 0 会穿透；`resource_retries = -1` 会让 `for (attemptIndex = 0; attemptIndex <= retries; …)` 一次都不执行，最终返回「未发起请求」的 network 失败。现在 `timeout` / `max_bytes` 要求「有限且为正」、`retries` 要求「非负整数」，越界一律回落默认（8000 / 1 / 16 MiB）；范围判定只在 http_client 一处，collector 不再重复实现同一规则。
  * **反证**（node：注入 fake fetch 与可抛错的 body reader；端到端：loopback 新增 `/stall/<ms>` 与 `/truncate`）：body 阶段 `TimeoutError` → `reason=timeout` 且重试一次、两次请求的 `AbortSignal` 不同；body 阶段普通读错误 → `reason=network` 且重试一次；`message` 恰为 `too-large` 但 `name` 普通 → 仍归 `network`（锁定「按 name 不按 message」）；`resource_retries=-1` / `resource_timeout_ms=0` / `resource_max_bytes=0` 都走默认值并真的发出请求 / 内嵌成功（不是零次请求、不是立刻超时、不是超限）。
  证据：`tests/test_renderer_network.py` 21 → 26 项、`renderer/test/http_client.test.js` 20 → 26 项；全套 `362 → 367 passed, 7 xfailed`；`--runxfail` 仍 `7 failed, 2 passed`；renderer `npm test` 61 → 67 passed；bundle 1,135,968 → 1,136,353 B。

- 2026-09-25（Phase 5D）：standalone closure —— 新 assembler + closure checker + 可执行矩阵 + opt-in 浏览器 smoke。**仍未切换 production renderer**：
  * **assembler**（新 `core/html_assembly.py`）：消费 v2 envelope 的 `html` / `headings` / `resources.styles` / `resources.scripts`，产出完整 HTML 并返回**注入账本**（`position` / `label` / `id` / `bytes`）。注入顺序确定且与 v1 逐项对齐：`<head>` = viewer.css → theme 链 → `resources.styles`（manifest 顺序）→ print.css；`</body>` 前 = viewer.js → numbering → 每个 script 条目的 `script` 后 `boot`。TOC 复用 `core/toc.py`（K14 形状已一致），标题经 `escape`。**`core/converter.py` 一行未改**：`_theme_body_class` 的 3 行逻辑在 assembler 内临时重复，注释写明 cutover checkpoint 再统一到 `core/config.py`。
  * **checker**（新 `tools/standalone_closure.py`，只用 stdlib `html.parser`，无新依赖）：扫描真正的 subresource（`img[src]`/`srcset`、`script[src]`、`link[href]`、`<style>` 内 `url(...)`；`<a href>` 导航与 `style="…"` 属性不计），输出四态 verdict + 逐条证据 + 体积报告；CLI `uv run python tools/standalone_closure.py <html> [--envelope …] [--author-refs …]`，`failure` 时退出码 1，缺 envelope 走 strict 模式。
  * **fallback-aware verdict**（K24）：`degraded` 与 `author_references` 分开，`failure` 只能由「既无 manifest/warning 证据、又未被声明为作者 raw HTML」产生 —— 于是「断网仍转换」和「standalone 零外链」不再互斥。`author` 声明必须被 renderer fragment 佐证，且声明本身**不能遮蔽 regression**（漏收集的 Markdown image、manifest 说 `inlined` 却仍是外链，都判 `failure`）。
  * **可执行矩阵**（`tests/test_standalone_matrix.py`）：普通 / KaTeX / Mermaid / remote 成功与失败 / PlantUML 成功与失败 / local 缺失 / local 无基准 / 作者 raw HTML / 双通道 / 生产基线，外加两个反证（凭空注入的引用；把 `inlined` 项换回原 URL）。生产基线 `samples/demo.html`（1,544,529 B）在 strict 扫描下是 `standalone`，而 checker 不搜 "http"（该页有 3 个 `<a href="http…">` 导航链接）。
  * **opt-in 浏览器 smoke**：`uv run python tools/assemble_document.py --out build/smoke.html` 装配一份集成页（普通文本 + KaTeX + Mermaid + 本地图片），再由 `pwsh tools/run_browser_acceptance.ps1 -ExtraPage build/smoke.html` 用真实 Edge 离线打开，断言 Mermaid `<svg>`、`.katex`、图片为 `data:`、非 `file://` 请求为 0、无 pageerror / unhandledrejection。不传 `-ExtraPage` 时该用例整条跳过（默认 5 项不变）。这条链当场发现一个真 bug：相对 `source_path` 会在 node 子进程里按 `renderer/` 解析，导致本地图片静默不内嵌；已修为绝对路径。
  * 明说未做的事：**没有新增任何 fetch 能力**；未接 Theme Registry / remote CSS / GUI options；未改 `templates/**`、未再生 `samples/demo.html`；**未切换 production renderer**（`core/renderer_node.py`、converter 默认实现、packaging、demo 再生、release/selfcheck、rollback 都属其后的 cutover checkpoint）。
  * cutover 前置项（登记，本阶段不实现）：`author_references` 目前依赖**显式声明**，生产 CLI 无声明时作者 raw HTML 外链会判 `failure`。生产级 provenance 建议在 cutover 时二选一：renderer 侧 additive 通道 `resources.author_references = [ref, …]`（只记来源，不抓取、不内嵌，K13 与 `items` 语义不变），或由持有源文件的 converter 做独立 characterization。**注意（5D closeout 修正）**：该通道必须**保留 occurrence 数量**（例如 `[{"ref": …, "count": n}, …]` 或每个 occurrence 一条记录），不能用去重集合 —— 同一 URL 可以同时来自作者 raw HTML 与 Markdown 图片，去重会让四态模型在真实混合文档里不闭合。**Cutover C1 已按第一种方案落地**（`resources.author_references` 采用 occurrence 形式，见 K25）。
  证据：新增 `tests/test_standalone_closure.py`（20 项）+ `tests/test_standalone_matrix.py`（18 项，含 smoke 生成器的相对路径回归锁）；全套 `367 → 405 passed, 7 xfailed`；`--runxfail` 仍 `7 failed, 2 passed`；`test_demo_generation.py` 7 passed（生产装配逐字节未变）；浏览器验收默认 5 passed + 1 skipped、带 `-ExtraPage` 6 passed；renderer `npm test` 仍 67（未改 JS）；ruff 全绿。

- 2026-09-25（Phase 5D checker reliability closeout）：修三项 checker 边界 + 两项 hardening。**只改 checker 与测试**（assembler / renderer / network / converter / production wiring 一行未动）：
  * **`srcset` 按规范解析**：原先按逗号 `split`，而 data URI 自带逗号 —— `srcset="data:image/png;base64,AAAA 1x"` 会被拆出伪引用 `AAAA`，把真正 standalone 的页面误判成 `failure`（原测试恰好还含一条真实外链，只断言最终 `failure`，把这个 bug 遮蔽了）。现在按 HTML 的 srcset 算法走 token：URL 是非空白串，候选在带尾逗号的 descriptor 或值结尾处结束，因此 data URI 里的逗号被保留；测试改为**显式断言 ref 列表**而不是只断言 verdict。
  * **`style="…"` 属性里的 CSS 参与扫描**：K13 的含义是「资源 collector 不修改 raw HTML」，不等于浏览器不会加载它。`<div style="background:url(https://…)"` 原先判 `standalone`，现在扫出 `origin=style-attr`：有 author 声明归 `author_references`，否则按正证据模型归 `failure`（**不要求 collector 抓取**）。生产基线不受影响：`samples/demo.html` 的 78 个 `style` 属性没有一个含 `url(`。
  * **证据按 occurrence 消费**（模型级修正）：manifest 本来就是每个 Markdown occurrence 一个 item（三次重复 URL → 三个 item），但原实现是 `ref -> 单个 item` + 去重声明集合，导致同一 URL 混用时判决错误：`inlined` manifest + 1 处声明 + 1 处外链被误判 `failure`；而 `failed` manifest + 1 处声明 + 2 处外链会把两处都算成 `degraded`。现在两侧都保留多重性（声明接受 `["url"]`、重复条目或 `{"ref": …, "count": n}`），并固定消费顺序 **`degraded → author → unexplained`**：degraded 先占位，所以 author 声明既不能把降级降级成 author，也不能吸收多余的 occurrence；warning 按 ref 共享（5C 对同一 URL 的同一失败只报一次），所以 `failed ×3 + warning ×1` 仍是 `degraded ×3`。报告新增 per-ref 账本 `occurrences[]`（`final` / `degraded` / `author` / `unexplained` / manifest 状态计数 / `declared_author` / `warning`），`subresources[].status` 按文档顺序回填。
  * **`link[href]` 按 `rel` 判定**（hardening）：只有会真的触发获取的 rel 才算 subresource（stylesheet / icon / preload / modulepreload / prefetch / manifest 等），canonical / alternate / author / license / dns-prefetch / preconnect 等忽略；**未知或缺失 `rel` 保守地按 subresource 处理**（宁可吵不可漏，已在模块 docstring 与 K24 写明）。
  * **`@import "x.css"` 字符串形式**（hardening）：`<style>` 内新增扫描；`@import url(...)` 原本已被 `url()` 覆盖，两者不重叠。
  * cutover 结论修正：author provenance 通道**不能是去重集合**，必须保留 occurrence 数量，否则这次建立的四态模型在真实混合文档里不闭合（已写进 5D 条目与 roadmap）。
  证据：`tests/test_standalone_closure.py` 20 → 33 项、`tests/test_standalone_matrix.py` 18 → 22 项；全套 `405 → 422 passed, 7 xfailed`；`--runxfail` 仍 `7 failed, 2 passed`；`samples/demo.html` strict 扫描仍 `standalone`（1,544,529 B，CLI exit 0）；ruff 全绿。

- 2026-09-25（Phase 5D checker closeout #2：mixed-rel `<link>` 优先级）：修一个会产出 **false `standalone`** 的边界。原实现 `return not (tokens & NON_FETCHING_LINK_RELS)` 让「任一 metadata token」导致整条 `<link>` 被忽略，于是标准写法 `<link rel="alternate stylesheet" href="…/theme.css" title="High contrast">` 被判 `standalone` —— 而 `alternate` 与 `stylesheet` 同时出现时它仍是 **external resource link**（只是非默认样式表）。现在改为三档优先级：① 出现 fetching token（`stylesheet` / `icon` / `preload` / `modulepreload` / `prefetch` / `manifest` / `apple-touch-icon(-precomposed)` / `mask-icon`）即为 subresource；② 全部为明确 metadata token（`canonical` / `alternate` / `author` / `license` / `dns-prefetch` / `preconnect` / `prev` / `next` / `search` / `tag` / `bookmark` / `help` / `me` / `pingback` / `webmention`）才忽略；③ 未知 / 缺失 / 混合未知一律按 subresource（保持「宁可吵不可漏」）。反证：`alternate stylesheet` 与 `author stylesheet` 都被扫描并判 `failure`，`dns-prefetch preconnect` 与 `canonical` 仍 `standalone`，`something-new` 仍按 subresource 处理。取向写进了 `_link_reference_is_fetched` 的 docstring（「不是默认」≠「不会被获取」），避免后来者按「alternate = 不加载」把它改回去。本仓产物不受影响：`samples/demo.html` 与 `templates/default/viewer.html` 的 `<link>` 数量都是 0。
  证据：`tests/test_standalone_closure.py` 33 → 37 项；全套 `422 → 426 passed, 7 xfailed`；`--runxfail` 仍 `7 failed, 2 passed`；`samples/demo.html` 仍 `standalone`；ruff 全绿。只改 checker、checker 测试与文档（assembler / renderer / network / converter / production wiring 未动）。
- 2026-09-25（Cutover C1：作者 raw HTML provenance 通道）：落地 5D 登记的 cutover 前置项（K25）。renderer 在 **token 层**（新 `renderer/document/author_references.js`，parse 后、render 前）记录作者自己写进文档的 raw HTML 外部 subresource 引用，产出 `resources.author_references = [{"ref": …, "count": n}, …]`：每 ref 一条、`count >= 1`、首次出现顺序、普通文档 `[]`。**为什么必须是 token 层**：从最终 html 反推无法区分作者 raw HTML 与 Markdown 生成的 html，5D 的四态模型会退化。**通道只记录来源**：不 fetch、不改 html、不进 `resources.items`（K13 边界不扩大），协议仍 v2（`emptyResources()` / `normalizeResources()` 白名单同步新增，`{"items","styles","scripts","author_references"}` 成为新的「必在」形状，5 处 Python 契约断言 + 1 处 node 断言随之更新）。
  * 规则与 checker 同构（`img[src]`/`srcset`、`script[src]`、`link[href]` + rel 三档、`<style>` 与 `style="…"` 的 `url(...)`、字符串 `@import`；`<a href>` 与 `data:` / `about:` / `#` 不算），并按 HTML 语义收紧两处：**HTML 注释与 `<script>` 内容不参与扫描**（注释 HTMLParser 不看、脚本内容是 CDATA），否则 `<!-- <img src=…> -->` 会声明一个最终 html 里不存在的引用、反把文档判成 `failure`。
  * checker 两项小改：`scan()` 在未显式给出声明时**自动消费** `envelope.resources.author_references`（`--author-refs` 仍优先，`--help` 已写明）；佐证计数改用 `collect_subresources(fragment)` 的抽取结果而不是裸 `html.count(ref)`，于是 `&amp;` 这类字符引用不再造成「声明了却对不上」。顺带把 `resources` 通道读取集中为 `_resources_channel()`（畸形 envelope 不再抛异常）。
  * 两侧共用 `tests/fixtures/author_references.json`（14 个 raw fragment + 8 个 document）作为对齐锚点：node 侧直测 scanner（合成 token）并 spawn dist 跑端到端，pytest 侧全部走真实 dist —— 任何一侧的规则漂移都会红。关键反证：`![m](url)` 绝不进入该通道（那是资源层 `items`）；同 URL 出现在 raw HTML + Markdown 图片时，通道只记 raw 的那一次（正是 5D occurrence 模型要区分的场景）。
  证据：新增 `tests/test_renderer_author_references.py`（27 项）+ `renderer/test/author_references.test.js`（24 项）；全套 `426 → 453 passed, 7 xfailed`；`--runxfail` = `7 failed, 453 passed`（旧 production 的 7 项 TARGET 仍严格 xfail）；renderer `npm test` 67 → 91；`uv run python tools/standalone_closure.py samples/demo.html` 仍 `standalone`（1,544,529 B）；ruff 全绿。未动 `core/**`（除测试桥 `tests/standalone_closure.py`）、`templates/**`、`samples/**`、`packaging/**` 与 GUI；C2–C4 未开始。


## texmath 审计记录（Phase 4B，为什么不复用 `markdown-it-texmath`）

`markdown-it-texmath@1.0.0` 的注册方式是固定的：

```js
md.inline.ruler.before('escape', rule.name, texmath.inline(rule));
md.renderer.rules[rule.name] = ...      // rule.name ∈ {math_inline, math_inline_double, math_block, math_block_eqno}
md.block.ruler.before('fence', rule.name, texmath.block(rule));
```

而 pinned 上游的 `markdown-it-katex.js` 用的正是同一组名字（inline `math_inline`、block `math_block`、`renderer.rules.math_inline` / `math_block`）与同一组 token 类型。因此只要把 texmath 装进同一个实例：

- 后注册的 texmath 会**覆盖** `renderer.rules.math_inline` / `math_block`，`$…$`（上游 token 化的结果）会被 texmath 的模板（`<eq>` / `<section><eqn>`）渲染 → `$` 的所有权被反转（AGENTS §2/§6）；
- 即便只启用 `brackets` + `beg_end` 两种 delimiter，渲染键的冲突依然存在；若只加载 texmath 的解析规则而不用它的 renderer，就等于在项目里复制一份上游插件。

结论：最薄的合规做法是 MarkdownReader 自己解析上游缺失的 delimiter，并复用**上游的 token 类型与 renderer**（即 `renderer/extensions/math_compat.js`）。
