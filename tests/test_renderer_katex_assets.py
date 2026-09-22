"""KaTeX assets are inlined only when a formula was actually rendered.

KaTeX ships roughly 1.4 MB of base64 fonts inside its stylesheet and the renderer
used to inline that stylesheet into every document, so a couple of kilobytes of
plain prose produced a 1.5 MB HTML file - and a hundred such documents wasted
some 140 MB of disk for nothing.

The decision is taken from the rendered HTML rather than from the Markdown
source, because a price such as $100, a dollar inside a code block and an escaped
dollar are text: a source level pattern would call them formulas and put the
fonts back.
"""

from pathlib import Path

import pytest

from core.renderer_node import render_markdown_node

FONT_FAMILY_MARKER = "KaTeX_AMS"
FONT_DATA_URI = "data:font/woff2"

# A code block and a price, both of which mention a dollar without being math.
_CODE_SNIPPET = '```python\nprint("Budget: $100; remaining: $200")\n```'


def _render(markdown: str, tmp_path: Path) -> dict:
    return render_markdown_node(
        markdown,
        context={
            "source_path": str(tmp_path / "doc.md"),
            "output_path": str(tmp_path / "doc.html"),
            "document_map": {},
        },
    )


def test_plain_prose_carries_no_katex_assets(tmp_path: Path):
    result = _render("只有普通文本，没有任何公式。", tmp_path)

    assert result["assets"]["css"] == ""
    assert 'class="katex' not in result["html"]


def test_a_dollar_in_code_or_as_a_price_is_not_a_formula(tmp_path: Path):
    """The cases a source level pattern would get wrong."""
    markdown = _CODE_SNIPPET + "\n\n价格 $100 美元，转义 \\$5。"

    result = _render(markdown, tmp_path)

    assert result["assets"]["css"] == "", "prose dollars must not pull in the fonts"
    assert 'class="katex' not in result["html"]


@pytest.mark.parametrize(
    "markdown",
    [
        "圆的面积 $A = \\pi r^2$ 适合嵌入解释。",
        "推导如下：\n\n$$\nE = mc^2\n$$\n",
    ],
    ids=["inline", "display"],
)
def test_a_formula_gets_the_self_contained_stylesheet(markdown: str, tmp_path: Path):
    result = _render(markdown, tmp_path)

    assert 'class="katex' in result["html"]
    assert FONT_FAMILY_MARKER in result["assets"]["css"]
    assert FONT_DATA_URI in result["assets"]["css"]


def test_malformed_formula_keeps_the_stylesheet(tmp_path: Path):
    """throwOnError leaves the source visible in red, which the CSS styles."""
    result = _render("坏公式 $\\frac{1}{$ 后面正常。", tmp_path)

    assert "katex-error" in result["html"]
    assert FONT_FAMILY_MARKER in result["assets"]["css"], (
        "error markup is still KaTeX markup and needs its stylesheet"
    )


def test_plain_prose_reports_no_new_warnings(tmp_path: Path):
    """Skipping the stylesheet is not an error path."""
    assert _render("普通文本。", tmp_path)["warnings"] == []
