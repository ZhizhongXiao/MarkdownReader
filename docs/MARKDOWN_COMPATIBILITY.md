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
| K8 | 脚注（引用、脚注区块、返回链接） | `keep/footnote` + `test_renderer_links.py` |
| K9 | KaTeX 预渲染：出现公式时得到 KaTeX HTML | `keep/math-inline-display` + `test_renderer_katex_assets.py` |
| K10 | Front Matter 只作 metadata，默认不进正文 | `test_front_matter.py`、`test_conversion_edge_cases.py` + `keep` 语料不含 front matter 的保证 |
| K11 | `fuzzyLink:false` 的既有语义：裸文件名与版本号保持文本 | `test_renderer_linkify.py` |
| K12 | `.md` / `.markdown` → `.html` 文档关系（含 fragment/query、未入清单 warning、消息可读） | `test_renderer_links.py`、`test_converter_integration.py` |
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
| G1 | checkbox | `type="checkbox"` 恰好 2 个，字面 `[ ] 未完成事项` 消失 | Phase 4 |
| G2 | mark | 出现 `<mark>`，字面 `==高亮文本==` 消失 | Phase 4 |
| G3 | callout | `[!NOTE]` 与 `[!WARNING]` 两个字面 marker 都消失、两段正文都保留，且出现可识别的提示块类名（只做 NOTE 不算通过） | Phase 4 |
| G4 | wikilink | 字面 `[[` 消失；`[[第二章]]` 与 `[[第二章\|别名显示]]` 都成为链接，可见文本分别为「第二章」「别名显示」，两个 href 均非空且 decode 后能识别目标「第二章」（不锁精确 URL 格式与 class） | Phase 4 |
| G5 | obsidian-tag | 标签带语义（`tag` 类名或 tag 链接），不再是纯文本 | Phase 4 |
| G6 | mermaid | `features.mermaid` 为真，且出现 `class="mermaid"` 运行时容器 | Phase 4/5 |
| G7 | plantuml | `features.plantuml` 为真，且进入图像资源流程（出现 `<img`） | Phase 4/5 |

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

## AGENTS §25 必测项覆盖映射

| 要求 | 证据 |
| --- | --- |
| Markdown 基础语法 | keep 语料（K2–K7） |
| checkbox / mark / Callout / WikiLink | TARGET G1–G4（xfail，Phase 4） |
| footnote | K8 |
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

## 变更记录

- 2026-09-24（Phase 1）：建立迁移语料、KEEP/TARGET 两组契约、锚点关系契约与本页；Phase 0 基线记录写入 [重构路线图](REFACTOR_ROADMAP.md)。
