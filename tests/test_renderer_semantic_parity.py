"""Phase 4A+4B 语义对照：old production renderer vs new adapter。

目的：在进入 Mermaid / PlantUML 之前，为「普通 Markdown + Phase 4A 新语法 + Phase 4B
compatibility」建立一层明确的 old/new 语义对照证据。这不是新功能阶段。

比较的是**产品级语义**，不是完整 HTML 字节。不比较：属性顺序、空白、heading slug 精确值
（TRANSITIONAL T5）、我们没有依赖的 upstream class 细节、KaTeX 内部 MathML 字节、
renderer 内部 token 顺序。

Phase 4A 新语法（checkbox / mark / callout / wikilink / obsidian-tag）在 old renderer 上本就
不支持，因此**不做** old == new：old 侧由 Phase 1 的 7 个 strict xfail 证明「仍不支持」，
new 侧由 tests/test_renderer_adapter_targets.py 证明「已实现」。features 通道只有新 adapter
有，同样不做 equality（见 test_features_are_adapter_only）。

资源层（local/remote image、KaTeX CSS/fonts、assets.css、Mermaid runtime、PlantUML 图像、
standalone 资源闭包）属于 Phase 5，明确排除在 parity 之外：old 更完整时记为 expected
pending，不算 Phase 4A/4B regression（见 test_resource_layer_differences_are_phase5_pending）。

已接受的差异只有一条：D1，由 test_accepted_dollar_pair_difference_is_explicit 显式表达；
其余 math 能力必须一致。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from markdown_fixtures import load_cases, read_fixture  # noqa: E402
from renderer_adapter import render  # noqa: E402
from test_renderer_adapter_keep import (  # noqa: E402
    ADAPTER_CASES,
    EXPECTED_KEEP_CASES,
    PENDING_CASES,
)
from test_renderer_adapter_targets import MIGRATED, PENDING  # noqa: E402

from core.renderer_node import render_markdown_node  # noqa: E402

HREF = re.compile(r"\shref=\"([^\"]*)\"")
BODY_HEADING = re.compile(r"<h([1-6])\s+id=\"([^\"]+)\"")
KATEX = 'class="katex'
UNLISTED = "未加入转换清单"


def render_old(markdown: str, context: dict | None = None) -> dict:
    """旧 production renderer（core/renderer_node → node_renderer/render.js）。"""
    result = render_markdown_node(markdown, context=context or {})
    return {
        "html": result["html"],
        "headings": result["headings"],
        "warnings": result["warnings"],
        "assets": result["assets"],
        # 旧 renderer 没有 features 通道：用 None 表示「不存在该契约」，不是空 dict。
        "features": None,
    }


def render_new(markdown: str, context: dict | None = None) -> dict:
    """新 adapter（renderer/dist/renderer.cjs）。"""
    return render(markdown, context=context or {})


def _virtual_context() -> dict:
    """纯字符串路径的转换上下文：parity 比较 renderer 语义，不依赖真实文件存在。"""
    base = "C:/parity/out"
    source = base + "/第24章.md"
    source_output = base + "/html/第24章.html"
    target_md = base + "/第20章 非货币性资产交换.md"
    target_markdown = base + "/第20章.markdown"
    return {
        "source_path": source,
        "output_path": source_output,
        "document_map": {
            source: source_output,
            target_md: base + "/html/第20章 非货币性资产交换.html",
            target_markdown: base + "/html/第20章.html",
        },
    }


def _hrefs(html: str) -> list[str]:
    """只取真实 href 属性；data-href="…" 里的子串不算。"""
    return HREF.findall(html)


def _body_heading_ids(html: str) -> list[str]:
    return [match.group(2) for match in BODY_HEADING.finditer(html)]


def _warning_facts(warnings: list[str], expected_path: str) -> dict:
    """把 warning 归纳为「数量 + 类别 + 可读路径」这类可比较事实，不比较完整文案。"""
    unlisted = [warning for warning in warnings if UNLISTED in warning]
    return {
        "total": len(warnings),
        "unlisted": len(unlisted),
        "readable_path": bool(unlisted) and all(expected_path in w for w in unlisted),
        "percent_encoded": any("%E7" in warning for warning in unlisted),
    }

# --- A. 基础 Markdown ------------------------------------------------------

BASIC_DOCUMENT = (
    "# 标题\n"
    "\n"
    "**粗体** 与 *斜体* 与 ~~删除线~~ 与 `code` 与 转义 \\*保持字面\\*。\n"
    "\n"
    "第一行\n第二行\n"
    "\n"
    "- 一级\n  - 二级\n    1. 三级有序\n"
    "\n"
    "| 左 | 右 |\n| :-- | --: |\n| a | b |\n"
    "\n"
    "```python\nprint(1)\n```\n"
    "\n"
    "> 引用\n"
    "\n"
    "行内 <span>raw</span> 与 <mark>raw mark</mark>。\n"
)

# 产品级语义标记：每项给出可接受的等价形式（例如删除线不锁定 <s> 还是 <del>）。
BASIC_MARKERS = (
    ("strong", ("<strong>粗体</strong>",)),
    ("emphasis", ("<em>斜体</em>",)),
    ("strike", ("<s>删除线</s>", "<del>删除线</del>")),
    ("inline-code", ("<code>code</code>",)),
    ("escaped-literal", ("*保持字面*",)),
    ("softbreak", ("<p>第一行\n第二行</p>",)),
    ("table", ("<table>",)),
    ("table-align-left", ('style="text-align:left"',)),
    ("table-align-right", ('style="text-align:right"',)),
    ("fence-language", ('class="language-python"',)),
    ("blockquote", ("<blockquote>",)),
    ("raw-span", ("<span>raw</span>",)),
    ("raw-mark", ("<mark>raw mark</mark>",)),
)


def _basic_marker_report(html: str) -> dict:
    return {name: any(option in html for option in options) for name, options in BASIC_MARKERS}


def test_basic_markdown_semantics_match():
    """同一输入下 old 与 new 必须出现同一组产品语义标记（不做整 HTML equality）。"""
    old = render_old(BASIC_DOCUMENT)
    new = render_new(BASIC_DOCUMENT)

    old_markers = _basic_marker_report(old["html"])
    new_markers = _basic_marker_report(new["html"])

    assert all(old_markers.values()), old_markers
    assert new_markers == old_markers, (new_markers, old_markers)
    assert new["html"].count("<ul>") == old["html"].count("<ul>") == 2
    assert new["html"].count("<ol>") == old["html"].count("<ol>") == 1
    assert [heading["text"] for heading in new["headings"]] == [
        heading["text"] for heading in old["headings"]
    ] == ["标题"]


# --- B. heading relationship ----------------------------------------------


def test_heading_relationship_holds_in_both_renderers():
    """K1 的关系契约两边成立；(level, text) 必须一致，anchor **文本**不作比较（T5）。"""
    case = next(case for case in load_cases("anchor") if case["group"] == "anchor")
    markdown = read_fixture(case)
    envelopes = {"old": render_old(markdown), "new": render_new(markdown)}

    for name, envelope in envelopes.items():
        headings = envelope["headings"]
        anchors = [heading["anchor"] for heading in headings]

        assert len(headings) == 8, name
        assert all(anchors), name
        assert len(set(anchors)) == len(anchors), name
        assert sorted(anchors) == sorted(_body_heading_ids(envelope["html"])), name
        assert "围栏里的标题" not in [heading["text"] for heading in headings], name
        assert all("#" not in heading["text"] for heading in headings), name

    old_sequence = [(heading["level"], heading["text"]) for heading in envelopes["old"]["headings"]]
    new_sequence = [(heading["level"], heading["text"]) for heading in envelopes["new"]["headings"]]

    assert new_sequence == old_sequence
    assert [level for level, _ in new_sequence] == [1, 2, 3, 2, 2, 2, 2, 2]


# --- C. linkify ------------------------------------------------------------


def test_linkify_contract_holds_in_both_renderers():
    """真实 URL 仍可点；裸文件名与版本号不得变成 URL（fuzzyLink 语义）。"""
    markdown = "访问 https://example.com 与 见 README.md 与 report.md 与版本 1.2.3。\n"

    for name, envelope in (("old", render_old(markdown)), ("new", render_new(markdown))):
        html = envelope["html"]

        assert 'href="https://example.com"' in html, name
        assert 'href="http:' not in html, name
        for bare in ("README.md", "report.md", "版本 1.2.3"):
            assert bare in html, (name, bare)


# --- D. footnote -----------------------------------------------------------


def test_footnote_structure_matches():
    """只锁可用结构（引用 / 区块 / 返回链接 / 字面消失），不锁编号字符串。"""
    case = next(case for case in load_cases("keep") if case["id"] == "footnote")
    markdown = read_fixture(case)

    for name, envelope in (("old", render_old(markdown)), ("new", render_new(markdown))):
        html = envelope["html"]

        assert 'class="footnote-ref"' in html, name
        assert 'class="footnotes"' in html, name
        assert 'class="footnote-backref"' in html, name
        assert "[^note]" not in html, name
        assert envelope["warnings"] == [], name
# --- E. document link ------------------------------------------------------

DOCUMENT_LINK_CASES = (
    ("known-md", "[第20章](<./第20章 非货币性资产交换.md>)\n"),
    ("known-markdown", "[第20章](./第20章.markdown)\n"),
    ("fragment-and-query", "[第20章](<./第20章 非货币性资产交换.md?view=1#第二节>)\n"),
    ("unselected", "[未选择章节](./第7章.md)\n"),
    ("internal-external-html", "[本节](#s) [网站](https://example.com) [旧](./第20章.html)\n"),
)


def test_document_link_href_parity():
    """真实 source/output/document_map 下，两种 renderer 必须产出同一组 href。"""
    context = _virtual_context()

    for case_id, markdown in DOCUMENT_LINK_CASES:
        old = render_old(markdown, context)
        new = render_new(markdown, context)

        assert sorted(_hrefs(new["html"])) == sorted(_hrefs(old["html"])), (
            case_id,
            _hrefs(old["html"]),
            _hrefs(new["html"]),
        )

    # href 相同还不足以说明「正确」：再单独确认两侧的产品级结果。
    known = render_new(DOCUMENT_LINK_CASES[0][1], context)["html"]
    assert ".html" in known and "%E7%AC%AC20%E7%AB%A0" in known
    assert ".md" not in known
    unselected = render_new(DOCUMENT_LINK_CASES[3][1], context)["html"]
    assert ".md" in unselected, "未选中目标必须保留作者写的 .md"


def test_unlisted_target_warning_parity():
    """warning 的数量、类别与可读路径必须一致；不要求完整文案逐字相同（K15 只锁可读性）。"""
    context = _virtual_context()
    markdown = "[未选择章节](./第7章.md)\n"

    old_facts = _warning_facts(render_old(markdown, context)["warnings"], "./第7章.md")
    new_facts = _warning_facts(render_new(markdown, context)["warnings"], "./第7章.md")

    assert old_facts == new_facts == {
        "total": 1,
        "unlisted": 1,
        "readable_path": True,
        "percent_encoded": False,
    }

    # heading 内的链接只警告一次：两个 renderer 都必须满足（新 adapter 会渲染两次 metadata）。
    heading = "# 参见[未选择章节](./missing.md)\n"
    for name, envelope in (
        ("old", render_old(heading, context)),
        ("new", render_new(heading, context)),
    ):
        assert sum(UNLISTED in warning for warning in envelope["warnings"]) == 1, (
            name,
            envelope["warnings"],
        )


# --- F. footnote + document link -------------------------------------------


def test_footnote_with_document_link_matches():
    """高价值组合：脚注定义里的链接也必须被改写，且不重复 warning。"""
    context = _virtual_context()
    markdown = (
        "正文[^chapter]\n"
        "\n"
        "[^chapter]: 参见[章节](<./第20章 非货币性资产交换.md#第二节>)。\n"
    )

    old = render_old(markdown, context)
    new = render_new(markdown, context)

    for name, envelope in (("old", old), ("new", new)):
        html = envelope["html"]

        assert 'class="footnote-ref"' in html, name
        assert 'class="footnotes"' in html, name
        assert envelope["warnings"] == [], (name, envelope["warnings"])
        assert any(".html#" in href for href in _hrefs(html)), (name, _hrefs(html))
        assert any("%E7%AC%AC%E4%BA%8C%E8%8A%82" in href for href in _hrefs(html)), name

    assert sorted(_hrefs(new["html"])) == sorted(_hrefs(old["html"]))
# --- G. math ---------------------------------------------------------------

# 「是否成为公式」必须一致的能力矩阵。D1（$100 与 $200）**不在**本表内：它是唯一已接受的
# 差异，由 test_accepted_dollar_pair_difference_is_explicit 显式表达。
MATH_MATRIX = (
    ("dollar-inline", "圆的面积 $A = \\pi r^2$ 适合嵌入解释。\n", True),
    ("dollar-display", "推导如下：\n\n$$\nE = mc^2\n$$\n", True),
    ("bracket-inline", "圆的面积 \\(A = \\pi r^2\\) 适合嵌入解释。\n", True),
    ("bracket-display", "推导如下：\n\n\\[\nE = mc^2\n\\]\n", True),
    ("environment-equation", "\\begin{equation}\nE = mc^2\n\\end{equation}\n", True),
    ("environment-align", "\\begin{align}\na &= b\n\\end{align}\n", True),
    ("single-dollar-is-text", "普通文本，价格 $100 美元。\n", False),
    ("escaped-dollar-is-text", "转义 \\$5 与 \\$6。\n", False),
    ("code-fence-keeps-math-syntax", "```\n$100\n\\(\n\\[\n```\n", False),
    ("unclosed-bracket-inline-is-text", "坏公式 \\(A = \\pi r^2 后面正常。\n", False),
    ("environment-star-is-text", "\\begin{align*}\na &= b\n\\end{align*}\n", False),
    ("environment-uppercase-is-text", "\\begin{Equation}\nE = mc^2\n\\end{Equation}\n", False),
    ("environment-mismatch-is-text", "\\begin{equation}\nE = mc^2\n\\end{align}\n", False),
    ("environment-indented-is-code", "    \\begin{equation}\nE = mc^2\n\\end{equation}\n", False),
    ("bracket-display-mid-paragraph-is-text", "文字 \\[a^2\\] 之后。\n", False),
    ("bracket-inline-multiline-is-text", "行内 \\(a^2 +\nb^2\\) 结束。\n", False),
)


def test_math_capability_matrix_matches_except_the_accepted_difference():
    """dollar / bracket / begin-end 与全部负例：old 与 new 的「是否成为公式」必须一致。"""
    mismatches = []

    for case_id, markdown, expected in MATH_MATRIX:
        old_formula = KATEX in render_old(markdown)["html"]
        new_formula = KATEX in render_new(markdown)["html"]
        if old_formula != expected or new_formula != expected:
            mismatches.append((case_id, old_formula, new_formula, expected))

    assert mismatches == [], mismatches


def test_accepted_dollar_pair_difference_is_explicit():
    """D1：唯一已接受的 old/new 差异，既锁定行为，也锁定它被登记而没有被测试遗漏。"""
    markdown = "价格 $100 与 $200 之间。\n"

    old_formula = KATEX in render_old(markdown)["html"]
    new_formula = KATEX in render_new(markdown)["html"]

    assert old_formula is False, "旧 texmath dollars 有空白保护，不把价格配成公式"
    assert new_formula is True, "pinned upstream 的 math_inline 会把它配成公式"

    registry = (ROOT / "docs" / "MARKDOWN_COMPATIBILITY.md").read_text(encoding="utf-8")
    assert "| D1 |" in registry
    assert "ACCEPTED UPSTREAM DIFFERENCE" in registry
    assert "$100 与 $200" in registry

    compat = (ROOT / "tests" / "test_renderer_adapter_compat.py").read_text(encoding="utf-8")
    assert "test_a_dollar_pair_across_prose_is_a_recorded_upstream_difference" in compat


# --- H/I/J. 注册表、features、资源层 ---------------------------------------


def test_migrated_and_pending_registries_are_locked():
    """KEEP 15/15 由 adapter 覆盖；Phase 4A 五项已迁移；Mermaid / PlantUML 仍 pending。"""
    assert tuple(MIGRATED) == ("checkbox", "mark", "callout", "wikilink", "obsidian-tag")
    assert tuple(PENDING) == ("mermaid", "plantuml")
    assert not set(MIGRATED) & set(PENDING)

    assert len(ADAPTER_CASES) == EXPECTED_KEEP_CASES == 15
    assert PENDING_CASES == {}, "KEEP 语料必须全部由新 adapter 覆盖"


def test_features_are_adapter_only():
    """features 没有 old 对等字段：只验证新 adapter 的语义，不做 old/new equality。"""
    markdown = (
        "- [ ] 任务\n"
        "\n"
        "==高亮==\n"
        "\n"
        "> [!NOTE]\n> 提示。\n"
        "\n"
        "[[目标]]\n"
        "\n"
        "#标签\n"
        "\n"
        "行内 $a^2$\n"
    )
    new = render_new(markdown)

    for key in ("checkbox", "mark", "callout", "wikilink", "obsidian_tag", "katex"):
        assert new["features"][key] is True, key

    assert render_old(markdown)["features"] is None, "旧 renderer 没有 features 通道"


def test_resource_layer_differences_are_phase5_pending():
    """资源层属 Phase 5：old 已有 assets 通道、new 尚无 —— expected pending，不是 regression。"""
    markdown = "![图](missing.png)\n"

    old = render_old(markdown)
    new = render_new(markdown)

    assert "assets" in old
    assert "assets" not in new, "新 adapter 的资源层属于 Phase 5，不在 parity 范围内"
    assert "missing.png" in new["html"], "资源层缺失不得导致引用丢失"
