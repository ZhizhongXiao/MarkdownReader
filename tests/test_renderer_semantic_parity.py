"""Renderer v2 semantic contracts retained from the former parity suite.

These checks preserve useful Markdown behavior while treating the supported
renderer as the only runtime oracle. Cross-version comparisons are no longer a
product contract; Git history and released QA records preserve that evidence.
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

HREF = re.compile(r"\shref=\"([^\"]*)\"")
BODY_HEADING = re.compile(r"<h([1-6])\s+id=\"([^\"]+)\"")
KATEX = 'class="katex'
UNLISTED = "未加入转换清单"


def render_v2(markdown: str, context: dict | None = None) -> dict:
    """Render offline through the production v2 adapter."""
    return render(
        markdown,
        options={"math": True},
        context=context or {},
    )


def _virtual_context() -> dict:
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
    return HREF.findall(html)


def _body_heading_ids(html: str) -> list[str]:
    return [match.group(2) for match in BODY_HEADING.finditer(html)]


def _warning_facts(warnings: list[str], expected_path: str) -> dict:
    unlisted = [warning for warning in warnings if UNLISTED in warning]
    return {
        "total": len(warnings),
        "unlisted": len(unlisted),
        "readable_path": bool(unlisted) and all(expected_path in warning for warning in unlisted),
        "percent_encoded": any("%E7" in warning for warning in unlisted),
    }


BASIC_DOCUMENT = (
    "# 标题\n\n"
    "**粗体** 与 *斜体* 与 ~~删除线~~ 与 `code` 与 转义 \\*保持字面\\*。\n\n"
    "第一行\n第二行\n\n"
    "- 一级\n  - 二级\n    1. 三级有序\n\n"
    "| 左 | 右 |\n| :-- | --: |\n| a | b |\n\n"
    "```python\nprint(1)\n```\n\n"
    "> 引用\n\n"
    "行内 <span>raw</span> 与 <mark>raw mark</mark>。\n"
)

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


def test_basic_markdown_semantics_are_preserved():
    envelope = render_v2(BASIC_DOCUMENT)
    html = envelope["html"]

    assert all(_basic_marker_report(html).values())
    assert html.count("<ul>") == 2
    assert html.count("<ol>") == 1
    assert [heading["text"] for heading in envelope["headings"]] == ["标题"]


def test_heading_contract_holds_for_the_supported_renderer():
    case = next(case for case in load_cases("anchor") if case["group"] == "anchor")
    envelope = render_v2(read_fixture(case))
    headings = envelope["headings"]
    anchors = [heading["anchor"] for heading in headings]

    assert len(headings) == 8
    assert all(anchors)
    assert len(set(anchors)) == len(anchors)
    assert sorted(anchors) == sorted(_body_heading_ids(envelope["html"]))
    assert "围栏里的标题" not in [heading["text"] for heading in headings]
    assert all("#" not in heading["text"] for heading in headings)
    assert [heading["level"] for heading in headings] == [1, 2, 3, 2, 2, 2, 2, 2]


def test_linkify_does_not_turn_bare_file_names_into_urls():
    envelope = render_v2("访问 https://example.com 与 README.md 与 report.md 与版本 1.2.3。\n")
    html = envelope["html"]

    assert 'href="https://example.com"' in html
    assert 'href="http:' not in html
    for bare in ("README.md", "report.md", "版本 1.2.3"):
        assert bare in html


def test_footnote_structure_is_preserved():
    case = next(case for case in load_cases("keep") if case["id"] == "footnote")
    envelope = render_v2(read_fixture(case))
    html = envelope["html"]

    assert 'class="footnote-ref"' in html
    assert 'class="footnotes"' in html
    assert 'class="footnote-backref"' in html
    assert "[^note]" not in html
    assert envelope["warnings"] == []


DOCUMENT_LINK_CASES = (
    ("known-md", "[第20章](<./第20章 非货币性资产交换.md>)\n"),
    ("known-markdown", "[第20章](./第20章.markdown)\n"),
    ("fragment-and-query", "[第20章](<./第20章 非货币性资产交换.md?view=1#第二节>)\n"),
    ("unselected", "[未选择章节](./第7章.md)\n"),
    ("internal-external-html", "[本节](#s) [网站](https://example.com) [旧](./第20章.html)\n"),
)


def test_markdown_document_links_follow_the_conversion_plan():
    context = _virtual_context()
    rendered = {
        case_id: render_v2(markdown, context)
        for case_id, markdown in DOCUMENT_LINK_CASES
    }

    known_hrefs = _hrefs(rendered["known-md"]["html"])
    assert len(known_hrefs) == 1
    assert ".html" in known_hrefs[0] and "%E7%AC%AC20%E7%AB%A0" in known_hrefs[0]
    assert ".md" not in known_hrefs[0]
    assert rendered["known-md"]["warnings"] == []

    markdown_hrefs = _hrefs(rendered["known-markdown"]["html"])
    assert len(markdown_hrefs) == 1 and markdown_hrefs[0].endswith(".html")
    fragment_hrefs = _hrefs(rendered["fragment-and-query"]["html"])
    assert len(fragment_hrefs) == 1
    assert ".html?view=1#" in fragment_hrefs[0]
    assert "%E7%AC%AC%E4%BA%8C%E8%8A%82" in fragment_hrefs[0]
    assert ".md" in _hrefs(rendered["unselected"]["html"])[0]
    assert _hrefs(rendered["internal-external-html"]["html"]) == [
        "#s",
        "https://example.com",
        "./%E7%AC%AC20%E7%AB%A0.html",
    ]


def test_unlisted_document_link_warning_is_readable_and_not_duplicated():
    context = _virtual_context()
    result = render_v2("[未选择章节](./第7章.md)\n", context)

    assert _warning_facts(result["warnings"], "./第7章.md") == {
        "total": 1,
        "unlisted": 1,
        "readable_path": True,
        "percent_encoded": False,
    }

    heading = render_v2("# 参见[未选择章节](./missing.md)\n", context)
    assert sum(UNLISTED in warning for warning in heading["warnings"]) == 1


def test_footnote_definition_keeps_document_link_rewriting():
    context = _virtual_context()
    markdown = (
        "正文[^chapter]\n\n"
        "[^chapter]: 参见[章节](<./第20章 非货币性资产交换.md#第二节>)。\n"
    )
    envelope = render_v2(markdown, context)
    html = envelope["html"]
    hrefs = _hrefs(html)

    assert 'class="footnote-ref"' in html
    assert 'class="footnotes"' in html
    assert envelope["warnings"] == []
    assert any(".html#" in href for href in hrefs)
    assert any("%E7%AC%AC%E4%BA%8C%E8%8A%82" in href for href in hrefs)


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


def test_math_capability_matrix_is_explicit_for_v2():
    mismatches = []
    for case_id, markdown, expected in MATH_MATRIX:
        rendered_as_formula = KATEX in render_v2(markdown)["html"]
        if rendered_as_formula is not expected:
            mismatches.append((case_id, rendered_as_formula, expected))
    assert mismatches == [], mismatches


def test_accepted_dollar_pair_difference_is_registered():
    envelope = render_v2("价格 $100 与 $200 之间。\n")

    assert KATEX in envelope["html"]
    assert envelope["features"]["katex"] is True
    registry = (ROOT / "docs" / "MARKDOWN_COMPATIBILITY.md").read_text(encoding="utf-8")
    assert "| D1 |" in registry
    assert "ACCEPTED UPSTREAM DIFFERENCE" in registry
    assert "$100 与 $200" in registry

    compat = (ROOT / "tests" / "test_renderer_adapter_compat.py").read_text(encoding="utf-8")
    assert "test_a_dollar_pair_across_prose_is_a_recorded_upstream_difference" in compat


def test_migrated_and_pending_semantic_registries_are_locked():
    assert tuple(MIGRATED) == (
        "checkbox",
        "mark",
        "callout",
        "wikilink",
        "obsidian-tag",
        "mermaid",
        "plantuml",
    )
    assert tuple(PENDING) == ()
    assert not set(MIGRATED) & set(PENDING)
    assert len(ADAPTER_CASES) == EXPECTED_KEEP_CASES == 15
    assert PENDING_CASES == {}


def test_v2_features_report_the_new_semantics():
    markdown = (
        "- [ ] 任务\n\n==高亮==\n\n> [!NOTE]\n> 提示。\n\n"
        "[[目标]]\n\n#标签\n\n行内 $a^2$\n"
    )
    envelope = render_v2(markdown)

    for key in ("checkbox", "mark", "callout", "wikilink", "obsidian_tag", "katex"):
        assert envelope["features"][key] is True, key


def test_resource_manifest_keeps_unresolved_local_image_references():
    envelope = render_v2("![图](missing.png)\n")

    assert set(envelope["resources"]) == {"items", "styles", "scripts", "author_references"}
    assert envelope["resources"]["items"] == [
        {"kind": "image", "source": "local", "ref": "missing.png", "status": "kept"}
    ]
    assert envelope["resources"]["styles"] == []
    assert envelope["resources"]["scripts"] == []
    assert "missing.png" in envelope["html"]
