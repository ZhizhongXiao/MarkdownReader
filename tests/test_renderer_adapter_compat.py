"""新 adapter 的 Phase 4B 兼容套件：footnote、额外数学分隔符、文档链接。

对照对象是旧 production renderer 的既有契约（tests/test_renderer_links.py、
tests/test_renderer_katex_assets.py、KEEP 语料 K8/K9），逐条在新 adapter 上重放。

所有权（AGENTS §6）：
  * $…$ / $$…$$  仍由 pinned upstream KaTeX 插件渲染；本套件锁「不得出现 texmath 包装」；
  * \\(…\\) / \\[…\\] / begin-end 由 MarkdownReader math compat 解析，渲染仍走
    upstream 的 renderer rule（token 类型是上游的 math_inline / math_block）；
  * footnote 是 MarkdownReader-owned（markdown-it-footnote，pinned 上游没有实现）；
  * `.md → .html` 与 WikiLink 目标解析属 document 层（renderer/document/links.js），
    只用 context 的 source_path / output_path / document_map，不搜文件系统。
"""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from markdown_fixtures import load_cases, read_fixture  # noqa: E402
from renderer_adapter import render  # noqa: E402

KATEX = 'class="katex'
KATEX_DISPLAY = 'class="katex-display"'
UNLISTED = "未加入转换清单"
HREF = re.compile(r"\shref=\"([^\"]*)\"")


def _keep_case(case_id: str) -> dict:
    cases = {case["id"]: case for case in load_cases("keep")}
    assert case_id in cases, case_id
    return cases[case_id]


def _context(source: Path, output: Path, mapping: dict | None = None) -> dict:
    return {
        "source_path": str(source),
        "output_path": str(output),
        "document_map": {str(key): str(value) for key, value in (mapping or {}).items()},
    }


def _only_selected(tmp_path: Path) -> tuple[Path, Path]:
    """建立一个「只选中自己」的转换上下文，用于「未选中目标」的对照。"""
    source = tmp_path / "第24章.md"
    source.write_text("", encoding="utf-8")
    return source, tmp_path / "html" / "第24章.html"


def _hrefs(html: str) -> list[str]:
    """只取真正的 href 属性；data-href="…" 里的子串不算。"""
    return HREF.findall(html)

# --- footnote（K8，MarkdownReader-owned） ---------------------------------


def test_footnote_keep_case_is_rendered_by_the_adapter():
    envelope = render(read_fixture(_keep_case("footnote")))
    html = envelope["html"]

    assert 'class="footnote-ref"' in html
    assert 'class="footnotes"' in html
    assert 'class="footnote-backref"' in html
    assert "[^note]" not in html
    assert envelope["warnings"] == []


def test_footnote_reference_without_a_definition_stays_text():
    envelope = render("正文提到 [^missing] 但没有定义。\n")

    assert "footnote-ref" not in envelope["html"]
    assert "[^missing]" in envelope["html"]


def test_document_links_inside_a_footnote_definition_are_rewritten(tmp_path: Path):
    """脚注定义会被 footnote_tail 搬到文末，其中的链接仍必须改写，且只警告一次。"""
    source = tmp_path / "第24章.md"
    target = tmp_path / "第20章 非货币性资产交换.md"
    source.write_text("", encoding="utf-8")
    target.write_text("", encoding="utf-8")
    source_output = tmp_path / "html" / "第24章.html"
    target_output = tmp_path / "html" / "第20章 非货币性资产交换.html"
    markdown = (
        "计量方法[^chapter]\n"
        "\n"
        "[^chapter]: 参见[第20章](<./第20章 非货币性资产交换.md#第二节>)。\n"
    )

    envelope = render(
        markdown,
        context=_context(source, source_output, {source: source_output, target: target_output}),
    )
    html = envelope["html"]

    assert 'class="footnote-ref"' in html and 'class="footnotes"' in html
    assert "%E7%AC%AC20%E7%AB%A0" in html
    assert ".html#%E7%AC%AC%E4%BA%8C%E8%8A%82" in html
    assert "[^chapter]" not in html
    assert envelope["warnings"] == []


# --- extra math（upstream 缺失的 delimiter） -------------------------------


def test_bracket_inline_formula_is_rendered_inline():
    envelope = render("圆的面积 \\(A = \\pi r^2\\) 适合嵌入解释。\n")
    html = envelope["html"]

    assert KATEX in html
    assert "katex-error" not in html
    assert envelope["features"]["katex"] is True


def test_bracket_display_formula_is_rendered_as_a_display_block():
    envelope = render("推导如下：\n\n\\[\nE = mc^2\n\\]\n")

    assert KATEX_DISPLAY in envelope["html"]


@pytest.mark.parametrize(
    ("environment", "body"),
    [("equation", "E = mc^2"), ("align", "a &= b")],
)
def test_environment_block_formula_is_rendered(environment: str, body: str):
    markdown = "\\begin{" + environment + "}\n" + body + "\n\\end{" + environment + "}\n"
    envelope = render(markdown)
    html = envelope["html"]

    # KaTeX 会把原始 TeX 放进 MathML 的 annotation，因此这里断言「成功排版」，
    # 而不是断言 TeX 文本从 HTML 中消失。
    assert KATEX_DISPLAY in html
    assert "katex-error" not in html
    assert envelope["features"]["katex"] is True


def test_dollar_math_still_belongs_to_the_upstream_renderer():
    """dollar 路径完全属于 pinned upstream：不得出现 texmath 的 <eq>/<eqn> 包装。"""
    inline = render("圆的面积 $A = \\pi r^2$ 适合嵌入解释。\n")["html"]
    display = render("推导如下：\n\n$$\nE = mc^2\n$$\n")["html"]

    assert KATEX in inline
    assert KATEX_DISPLAY in display
    assert "<eq>" not in inline and "<eqn>" not in display


NOT_FORMULAS = (
    ("price", "普通文本，价格 $100 美元，转义 \\$5。\n"),
    ("escaped-dollar", "转义 \\$5 与 \\$6。\n"),
    ("code-fence", "```\n$100\n\\(\n\\[\n```\n"),
    ("unclosed-bracket-inline", "坏公式 \\(A = \\pi r^2 后面正常。\n"),
    ("bare-backslash", "文本 \\frac{1}{2} 与单独的 \\ 符号。\n"),
    ("environment-star", "\\begin{align*}\na &= b\n\\end{align*}\n"),
    ("environment-uppercase", "\\begin{Equation}\nE = mc^2\n\\end{Equation}\n"),
    ("environment-mismatch", "\\begin{equation}\nE = mc^2\n\\end{align}\n"),
    ("bracket-display-mid-paragraph", "文字 \\[a^2\\] 之后。\n"),
    ("bracket-inline-multiline", "行内 \\(a^2 +\nb^2\\) 结束。\n"),
    ("indented-environment", "    \\begin{equation}\nE = mc^2\n\\end{equation}\n"),
)


@pytest.mark.parametrize(
    "markdown",
    [markdown for _, markdown in NOT_FORMULAS],
    ids=[case_id for case_id, _ in NOT_FORMULAS],
)
def test_extra_delimiters_never_turn_text_into_a_formula(markdown: str):
    envelope = render(markdown)

    assert KATEX not in envelope["html"]
    assert envelope["features"]["katex"] is False


def test_a_dollar_pair_across_prose_is_a_recorded_upstream_difference():
    """已记录的上游差异：upstream 的 $ 规则没有 texmath 的 pre/post 保护。

    旧 production renderer 用 markdown-it-texmath 的 dollars 规则，要求 $…$ 的内容不以空白
    结尾，因此「价格 $100 与 $200 之间。」不是公式；pinned upstream 的 math_inline 只跳过转义
    与空的 $$，会把首尾两个 $ 配成公式。$ 路径属 upstream（AGENTS §6：不得形成第二套
    $…$ parser），本阶段不修改该行为，只把它锁定为可见差异；记录见
    docs/MARKDOWN_COMPATIBILITY.md「已知差异」。
    """
    envelope = render("价格 $100 与 $200 之间。\n")

    assert KATEX in envelope["html"], "记录当前行为：上游规则或迁移决策改变时这里必须失败"
    assert envelope["features"]["katex"] is True


def test_katex_feature_ignores_a_handwritten_lookalike():
    envelope = render('<span class="katex">raw</span>\n')

    assert KATEX in envelope["html"]
    assert envelope["features"]["katex"] is False


def test_katex_feature_stays_true_for_a_malformed_formula():
    envelope = render("坏公式 $\\frac{1}{$ 后面正常。\n")

    assert "katex-error" in envelope["html"]
    assert envelope["features"]["katex"] is True


def test_math_false_keeps_every_delimiter_as_text():
    envelope = render("公式 \\(a^2\\) 与 $a^2$\n", options={"math": False})

    assert KATEX not in envelope["html"]
    assert envelope["features"]["katex"] is False
    assert any("math=false" in warning for warning in envelope["warnings"])

# --- document links（K12，document 层） -----------------------------------


def test_known_markdown_target_is_rewritten_to_the_planned_html(tmp_path: Path):
    source = tmp_path / "第24章.md"
    target = tmp_path / "第20章 非货币性资产交换.md"
    source.write_text("", encoding="utf-8")
    target.write_text("", encoding="utf-8")
    source_output = tmp_path / "html" / "第24章.html"
    target_output = tmp_path / "html" / "第20章 非货币性资产交换.html"

    envelope = render(
        "[第20章](<./第20章 非货币性资产交换.md>)\n",
        context=_context(source, source_output, {source: source_output, target: target_output}),
    )
    hrefs = _hrefs(envelope["html"])

    assert len(hrefs) == 1, envelope["html"]
    assert hrefs[0].startswith("./")
    assert unquote(hrefs[0]) == "./第20章 非货币性资产交换.html"
    assert envelope["warnings"] == []


def test_markdown_extension_variant_keeps_query_and_fragment(tmp_path: Path):
    source = tmp_path / "book" / "第24章.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "book" / "第20章.markdown"
    source.write_text("", encoding="utf-8")
    target.write_text("", encoding="utf-8")
    source_output = tmp_path / "out" / "第24章.html"
    target_output = tmp_path / "out" / "第20章.html"

    envelope = render(
        "[第20章](./第20章.markdown?view=1#第二节)\n",
        context=_context(source, source_output, {source: source_output, target: target_output}),
    )

    assert _hrefs(envelope["html"]) == [
        "./%E7%AC%AC20%E7%AB%A0.html?view=1#%E7%AC%AC%E4%BA%8C%E8%8A%82"
    ]
    assert envelope["warnings"] == []


def test_unselected_target_keeps_the_written_href_and_warns_readably(tmp_path: Path):
    source, output = _only_selected(tmp_path)

    markdown = "[未选择章节](./第7章.md)\n"
    envelope = render(markdown, context=_context(source, output, {source: output}))
    warnings = [warning for warning in envelope["warnings"] if UNLISTED in warning]

    assert ".md" in envelope["html"]
    assert len(warnings) == 1, envelope["warnings"]
    assert "./第7章.md" in warnings[0]
    assert "%E7" not in warnings[0], "warning 必须显示作者写下的文字"


def test_internal_external_and_html_links_are_untouched(tmp_path: Path):
    source, output = _only_selected(tmp_path)

    envelope = render(
        "[本节](#section) [网站](https://example.com) [协议相对](//example.com/x.md)"
        " [旧 HTML](./第20章.html)\n",
        context=_context(source, output, {source: output}),
    )
    html = envelope["html"]

    assert 'href="#section"' in html
    assert 'href="https://example.com"' in html
    assert "//example.com/x.md" in html
    assert "%E7%AC%AC20%E7%AB%A0.html" in html
    assert envelope["warnings"] == []


def test_a_heading_link_is_reported_once(tmp_path: Path):
    """heading 会被 collectHeadings 单独渲染一次；warning 不得因此重复。"""
    source, output = _only_selected(tmp_path)

    envelope = render(
        "# 参见[未选择章节](./missing.md)\n", context=_context(source, output, {source: output})
    )

    assert sum(UNLISTED in warning for warning in envelope["warnings"]) == 1
    assert envelope["headings"][0]["inline_html"].count("missing.md") == 1


def test_a_malformed_percent_sequence_is_reported_without_failing(tmp_path: Path):
    source, output = _only_selected(tmp_path)

    envelope = render(
        "[坏编码](./broken%E0%A4%A.md)\n", context=_context(source, output, {source: output})
    )
    warnings = [warning for warning in envelope["warnings"] if UNLISTED in warning]

    assert len(warnings) == 1
    assert "./broken%E0%A4%25A.md" in warnings[0]
    assert ".md" in envelope["html"]


# --- WikiLink 目标解析（只用 document_map，不搜文件系统） ------------------


def _wiki_context(tmp_path: Path, pages: dict[str, Path]) -> dict:
    """建立「第24章 + 若干已选中目标」的转换上下文。"""
    source = tmp_path / "第24章.md"
    source.write_text("", encoding="utf-8")
    source_output = tmp_path / "html" / "第24章.html"
    mapping = {source: source_output}
    for page, target in pages.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
        mapping[target] = tmp_path / "html" / (page + ".html")
    return _context(source, source_output, mapping)


def test_wikilink_resolves_to_a_planned_document(tmp_path: Path):
    context = _wiki_context(tmp_path, {"第20章": tmp_path / "第20章.md"})

    envelope = render("参见 [[第20章]] 与 [[第20章.md]]。\n", context=context)

    assert _hrefs(envelope["html"]) == ["./%E7%AC%AC20%E7%AB%A0.html"] * 2, envelope["html"]
    assert envelope["warnings"] == []


def test_wikilink_alias_and_fragment_are_preserved(tmp_path: Path):
    context = _wiki_context(tmp_path, {"第20章": tmp_path / "第20章.md"})

    envelope = render("参见 [[第20章#第二节|别名显示]]。\n", context=context)

    assert _hrefs(envelope["html"]) == ["./%E7%AC%AC20%E7%AB%A0.html#%E7%AC%AC%E4%BA%8C%E8%8A%82"]
    assert "别名显示</a>" in envelope["html"]


def test_wikilink_with_a_relative_path_target_is_resolved(tmp_path: Path):
    context = _wiki_context(tmp_path, {"章节/第20章": tmp_path / "章节" / "第20章.md"})

    envelope = render("参见 [[章节/第20章]]。\n", context=context)

    assert _hrefs(envelope["html"]) == ["./%E7%AB%A0%E8%8A%82/%E7%AC%AC20%E7%AB%A0.html"]


def test_unresolved_wikilink_keeps_the_phase4a_fallback_without_a_warning(tmp_path: Path):
    source, output = _only_selected(tmp_path)

    markdown = "参见 [[没选中的章节]]。\n"
    envelope = render(markdown, context=_context(source, output, {source: output}))

    assert _hrefs(envelope["html"]) == ["#%E6%B2%A1%E9%80%89%E4%B8%AD%E7%9A%84%E7%AB%A0%E8%8A%82"]
    assert envelope["warnings"] == [], "未选中不等于错误：WikiLink 解析不新增 warning"


def test_ambiguous_wikilink_target_is_not_guessed(tmp_path: Path):
    """同名 .md 与 .markdown 都被选中时有两个候选，不猜。"""
    context = _wiki_context(
        tmp_path,
        {"第20章-a": tmp_path / "第20章.md", "第20章-b": tmp_path / "第20章.markdown"},
    )

    envelope = render("参见 [[第20章]]。\n", context=context)

    assert _hrefs(envelope["html"]) == ["#%E7%AC%AC20%E7%AB%A0"]
    assert envelope["warnings"] == []


def test_wikilink_resolution_never_scans_the_filesystem(tmp_path: Path):
    """目标文件真实存在于磁盘，但不在本次转换清单里，不得解析。"""
    source = tmp_path / "第24章.md"
    target = tmp_path / "第20章.md"
    source.write_text("", encoding="utf-8")
    target.write_text("", encoding="utf-8")
    output = tmp_path / "html" / "第24章.html"

    envelope = render("参见 [[第20章]]。\n", context=_context(source, output, {source: output}))

    assert _hrefs(envelope["html"]) == ["#%E7%AC%AC20%E7%AB%A0"]
    assert envelope["warnings"] == []
