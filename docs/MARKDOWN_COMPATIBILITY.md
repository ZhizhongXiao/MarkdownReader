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
| K16 | standalone HTML 装配（自包含、标题转义、无 CDN） | `test_demo_generation.py`、`test_converter_integration.py` |
| K17 | Viewer / 索引页 / GUI 行为契约 | `tests/js` 层：viewer 22、index 9、GUI 9、selfcheck 5 |
| K18 | 运行时归属与可靠调用：打包物只使用内置 Node（不借 PATH）、渲染前冒烟自检。**进程粒度不是契约**（见 IMPLEMENTATION DETAIL） | `test_node_runtime.py`（5 项） |
| K19 | 覆盖语义：`overwrite=false` 跳过并保留原文件 | `test_conversion_edge_cases.py` |
| K20 | 发布门禁与产物校验 | `test_release_freeze.py`、`test_release_validation.py` |
| K21 | 按需载荷：有公式才携带 KaTeX 资产，无公式不携带（体积纪律）。**具体信封键名不是契约** | `test_renderer_katex_assets.py`、`test_converter_integration.py` |

## TRANSITIONAL：记录现状，路线图已定要改

| # | 今天的真实行为 | 何时改 | 涉及测试 → 处理约定 |
| --- | --- | --- | --- |
| T1 | remote image **永远**保留原 URL | Phase 5：联网尝试内嵌，失败保留 URL + warning | `test_image_embedding.py::test_remote_image_is_left_untouched` 必须**显式改写**，并在本表登记原因 |
| T2 | 单一 `template` 选择、`extends` 继承链、`theme-<id>` body class | Phase 6–8：Theme registry、三个 builtin 常驻、`external_themes` | `test_demo_generation.py`、`test_template_style_contract.py` |
| T3 | `config.json` 的 `build.template`，配置与日志位于 EXE 同级 | Phase 8 / Phase 10：`external_themes` + `profile/` | 配置 schema 与 `test_gui_state_contract.py` |
| T4 | `samples/demo.html` 必须等于当前源码的输出 | Phase 4/6 输出必然变化：重新生成并在提交说明里解释 | `test_demo_generation.py::test_demo_html_matches_the_committed_specimen` |
| T5 | 标题 slug 的**精确值**（今天由 `slugifyUnicode` 给出） | Phase 4：允许按 vscode-office / markdown-it-anchor 对齐 | **不作断言**；诊断记录见下表 |
| T6 | Python TOC → Viewer 的 DOM contract：`data-explicit-number`（Viewer 据此标记“已编号”标题） | Phase 6：可以重新设计，但必须同步修改 producer（core/toc.py）、consumer（templates/viewer.js）与相关测试，并在本表登记 | Viewer NUM1/NUM2、`test_toc_heading_contract.py` |
| T7 | KaTeX 资产以单个 `assets.css` 全量内联 | Phase 3 adapter 可能改为更细的资源协议 | 断言只锁“有公式才有载荷、离线可用” |

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
| G6 | mermaid | `features.mermaid` 为真，且出现 `class="mermaid"` 运行时容器 | **仍 pending**（Phase 4C/5）：features 恒 false，未注入 runtime |
| G7 | plantuml | `features.plantuml` 为真，且进入图像资源流程（出现 `<img`） | **仍 pending**（Phase 4C/5）：features 恒 false，不建网络资源层 |

Phase 1 **只锁产品级语义，不锁尚未 pin 住的上游 DOM**。Callout 与 Obsidian tag 先接受一个允许集合（`callout`/`admonition`/`markdown-alert`/`alert`/`note`；tag 类名或 `tag` 链接）；Phase 2 固定 vscode-office commit、Phase 3 adapter 定型之后，再补确实需要的上游 DOM contract。

## IMPLEMENTATION DETAIL：允许重构

`render.js` 的文件布局与内部函数名（`installHeadingIds`、`slugifyUnicode`、`resolveImageSource`、`rewriteDocumentHref`、`decodeForDisplay`…）、`assets.css` 信封键名、`warnings` 文案（除“路径可读”这一产品要求）、CSS/JS 注入位置、`linkify.set()` 的调用形式、`templates/Modern` 目录名与 id `modern` 的大小写依赖、`_theme_body_class` 的具体类名、每文档一个 Node 进程。

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

**D1 决策理由**（Phase 4A+4B closeout 明确接受，不修改）：

- `$…$` / `$$…$$` 的 ownership 已归 pinned vscode-office；
- 不在 MarkdownReader 内创建第二套 dollar parser，也不加 before-rule guard 去重新解释 `$`；
- 后续如需改变，应优先通过 upstream issue / contribution / upstream commit 更新解决。

行为由 `tests/test_renderer_adapter_compat.py::test_a_dollar_pair_across_prose_is_a_recorded_upstream_difference` 锁定（**不得**改回「旧行为必须保持」），并由 `tests/test_renderer_semantic_parity.py::test_accepted_dollar_pair_difference_is_explicit` 同时锁定「它已被登记」。

KEEP 契约未受影响：`keep/plain-text-no-math` 用的是单个未配对 `$` 与转义 `\$`，adapter 上仍然不产生公式（该 case 由 `test_renderer_adapter_keep.py` 覆盖）。

除 D1 之外，本次 closeout 未发现其它 old/new 语义差异：math 能力矩阵的其余 16 个样本（含全部负例）两边一致（`test_math_capability_matrix_matches_except_the_accepted_difference`）。

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
| H/I/J 注册表与范围 | `test_migrated_and_pending_registries_are_locked`、`test_features_are_adapter_only`、`test_resource_layer_differences_are_phase5_pending` | KEEP 15/15、Phase 4A 五项已迁移、Mermaid / PlantUML 仍 pending、features 只属 adapter、资源层记为 Phase 5 pending |

比较范围之外（Phase 5）：local image data URI、remote image、KaTeX CSS/fonts 载荷、`assets.css`、Mermaid runtime、PlantUML 图像、standalone 资源闭包。old renderer 在这些项上更完整，属 expected pending，**不算** Phase 4A/4B regression。

当前数字（按套件）：`test_renderer_semantic_parity.py` 12、`test_renderer_adapter_keep.py` 20、`test_renderer_adapter_targets.py` 14（4A 条目里的 13 项是那次提交当时的计数）、`test_renderer_adapter_compat.py` 35。

全套：`uv run pytest -q` → 266 passed, 7 xfailed；renderer `npm test` → 6 passed；`uv run pytest -q --runxfail tests/test_markdown_compat_target.py` → `7 failed, 2 passed`（TARGET 门禁仍是 strict xfail）；`uv run ruff check .` → All checks passed。

## AGENTS §25 必测项覆盖映射

| 要求 | 证据 |
| --- | --- |
| Markdown 基础语法 | keep 语料（K2–K7） |
| checkbox / mark / Callout / WikiLink | TARGET G1–G4（xfail，Phase 4） |
| footnote | K8 |
| footnote / 额外数学分隔符 / 文档链接（adapter 侧） | Phase 4B：`tests/test_renderer_adapter_compat.py`（35 项） |
| KEEP 语料在 adapter 上的对照 | `tests/test_renderer_adapter_keep.py`（20 项，15/15 KEEP case 全覆盖，footnote 于 Phase 4B 补齐） |
| KaTeX | K9 |
| Mermaid / PlantUML | TARGET G6–G7 |
| local image / remote image | K13（remote 同时登记为 T1） |
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
