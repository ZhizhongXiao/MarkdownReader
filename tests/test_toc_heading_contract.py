"""TOC heading contract.

A TOC title reuses the inline Markdown semantics of its body heading, with two
deliberate downgrades for content that must not be embedded in a TOC
navigation link: links become their visible text and images become their alt
text.

Links and images are downgraded in both their Markdown form and their raw HTML
form, while other raw HTML such as <b> is rendered as-is.

The expectations in TOC_EXPECTATIONS and TOC_INLINE_HTML_EXPECTATIONS are
written out per heading on purpose. They describe the product contract, so the
tests never re-implement number splitting or inline rendering to derive an
expected value.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.converter as converter  # noqa: E402
from core.renderer_node import render_markdown_node  # noqa: E402

CONFIG = {"template": "modern", "numbering": False, "overwrite": True}

# Heading inline source, expected .toc-number, expected .toc-title HTML, and
# the known defect reason (empty once the contract holds).
TOC_EXPECTATIONS = [
    ("a < b", "", "a &lt; b", "known: plain text is re-interpreted as HTML"),
    ("a & b", "", "a &amp; b", "known: plain text is re-interpreted as HTML"),
    ("*emphasis*", "", "<em>emphasis</em>", ""),
    ("**strong**", "", "<strong>strong</strong>", "known: the TOC re-renders inline Markdown"),
    ("`code`", "", "<code>code</code>", ""),
    ("a <b>x</b> y", "", "a <b>x</b> y", ""),
    ("[link](https://example.com)", "", "link", "known: heading links are not downgraded"),
    ("![alt](x.png)", "", "alt", "known: heading images keep their Markdown source"),
    ("![](x.png)", "", "", "known: heading images keep their Markdown source"),
    ("1.2 Plain", "1.2", "Plain", ""),
    ("1.2 *emphasis*", "1.2", "<em>emphasis</em>", ""),
    (
        "**1.2** unusual",
        "",
        "<strong>1.2</strong> unusual",
        "known: the TOC re-renders inline Markdown",
    ),
    (
        '<a href="https://example.com">link</a>',
        "",
        "link",
        "known: raw HTML anchors are not downgraded",
    ),
    (
        '<img src="x.png" alt="alt">',
        "",
        "alt",
        "known: raw HTML images keep their markup",
    ),
]

HEADING_SOURCES = [markdown for markdown, _, _, _ in TOC_EXPECTATIONS]

# Expected toc_inline_html per heading inline source: the full TOC-safe
# inline HTML before number splitting. Markdown and raw HTML links become their
# visible content; Markdown and raw HTML images become their alt text.
TOC_INLINE_HTML_EXPECTATIONS = [
    ("a < b", "a &lt; b"),
    ("a & b", "a &amp; b"),
    ("*emphasis*", "<em>emphasis</em>"),
    ("**strong**", "<strong>strong</strong>"),
    ("`code`", "<code>code</code>"),
    ("a <b>x</b> y", "a <b>x</b> y"),
    ("[link](https://example.com)", "link"),
    ("![alt](x.png)", "alt"),
    ("![](x.png)", ""),
    ("1.2 Plain", "1.2 Plain"),
    ("1.2 *emphasis*", "1.2 <em>emphasis</em>"),
    ("**1.2** unusual", "<strong>1.2</strong> unusual"),
    ('<a href="https://example.com">link</a>', "link"),
    ('<img src="x.png" alt="alt">', "alt"),
]


def _toc_params():
    """Parametrize the TOC cases, marking each known defect separately."""
    params = []
    for markdown, number, title, defect in TOC_EXPECTATIONS:
        marks = ()
        if defect:
            marks = (pytest.mark.xfail(strict=True, raises=AssertionError, reason=defect),)
        params.append(pytest.param(markdown, number, title, marks=marks, id=markdown))
    return params


def _convert(tmp_path: Path, markdown: str) -> str:
    """Convert a single heading into a document and return the generated HTML."""
    source = tmp_path / "heading.md"
    source.write_text("# " + markdown + "\n", encoding="utf-8")
    output = tmp_path / "heading.html"
    result = converter.process_single(str(source), str(output), CONFIG)
    if result is None:
        raise RuntimeError("conversion produced no output for " + markdown)
    return output.read_text(encoding="utf-8")


def _toc_field(html: str, field: str) -> str:
    """Return the content of the first TOC span with the given class name."""
    marker = '<span class="' + field + '">'
    start = html.index(marker) + len(marker)
    return html[start : html.index("</span>", start)]


@pytest.mark.parametrize("markdown", HEADING_SOURCES, ids=HEADING_SOURCES)
def test_heading_metadata_is_well_formed(markdown: str):
    headings = render_markdown_node("# " + markdown + "\n")["headings"]

    assert len(headings) == 1
    assert headings[0]["level"] == 1
    assert headings[0]["anchor"]


@pytest.mark.parametrize("markdown", HEADING_SOURCES, ids=HEADING_SOURCES)
def test_heading_text_keeps_the_raw_inline_source(markdown: str):
    headings = render_markdown_node("# " + markdown + "\n")["headings"]

    assert headings[0]["text"] == markdown


def _multi_heading_document() -> str:
    """Return one document that contains every heading source in order."""
    return ("\n\n").join("# " + markdown for markdown in HEADING_SOURCES)


def _body_heading_html(html: str) -> list:
    """Return the inline HTML of every level-1 heading in the rendered body."""
    return re.findall("<h1[^>]*>(.*?)</h1>", html, re.S)


@pytest.mark.xfail(
    strict=True,
    raises=KeyError,
    reason="known: heading metadata does not expose inline_html yet",
)
def test_heading_metadata_exposes_inline_html():
    rendered = render_markdown_node(_multi_heading_document())
    headings = rendered["headings"]
    body = _body_heading_html(rendered["html"])

    assert len(headings) == len(HEADING_SOURCES)
    assert len(body) == len(HEADING_SOURCES)
    for heading, expected in zip(headings, body):
        assert heading["inline_html"] == expected


@pytest.mark.xfail(
    strict=True,
    raises=KeyError,
    reason="known: heading metadata does not expose toc_inline_html yet",
)
def test_heading_metadata_exposes_toc_inline_html():
    headings = render_markdown_node(_multi_heading_document())["headings"]

    assert len(headings) == len(TOC_INLINE_HTML_EXPECTATIONS)
    for heading, (_, expected) in zip(headings, TOC_INLINE_HTML_EXPECTATIONS):
        assert heading["toc_inline_html"] == expected


@pytest.mark.parametrize("markdown, expected_number, expected_title", _toc_params())
def test_toc_row_follows_the_heading_contract(
    tmp_path: Path, markdown: str, expected_number: str, expected_title: str
):
    html = _convert(tmp_path, markdown)

    assert _toc_field(html, "toc-number") == expected_number
    assert _toc_field(html, "toc-title") == expected_title
