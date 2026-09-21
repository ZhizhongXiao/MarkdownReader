"""Regression contracts for conversion edge cases.

The tests marked xfail(strict=True) document known defects that are scheduled
for a later fix. They also pin the failure type via raises=, so an unrelated
error (missing template, missing Node.js, broken helper) surfaces as a normal
failure instead of being swallowed by the marker.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.converter as converter  # noqa: E402
from core.conversion_plan import build_conversion_plan  # noqa: E402

BASE_CONFIG = {"template": "modern", "numbering": False, "overwrite": False}


class ExpectedRenderFailure(RuntimeError):
    """Raised by the fake renderer to simulate a single-document failure."""


def _convert(tmp_path: Path, name: str, text: str, cfg: dict, encoding: str = "utf-8") -> str:
    """Convert one Markdown file and return the generated HTML."""
    source = tmp_path / name
    source.write_text(text, encoding=encoding)
    output = tmp_path / (source.stem + ".html")
    result = converter.process_single(str(source), str(output), cfg)
    if result is None:
        raise RuntimeError("conversion produced no output for " + name)
    return output.read_text(encoding="utf-8")


def _document_title(html: str) -> str:
    """Return the text of the document title element."""
    start = html.index("<title>") + len("<title>")
    return html[start : html.index("</title>", start)]


def _toc_title(html: str) -> str:
    """Return the first TOC title span content."""
    marker = '<span class="toc-title">'
    start = html.index(marker) + len(marker)
    return html[start : html.index("</span>", start)]


def _body_heading_title(html: str) -> str:
    """Return the inline HTML of the first level-1 heading in the article body."""
    start = html.index('<article class="markdown-body"')
    open_tag = html.index("<h1", start)
    content_start = html.index(">", open_tag) + 1
    return html[content_start : html.index("</h1>", content_start)]


def test_front_matter_is_read_when_the_file_starts_with_a_bom(tmp_path: Path):
    html = _convert(
        tmp_path,
        "bom.md",
        "---\ntitle: MetaTitle\n---\n\n# Body\n",
        dict(BASE_CONFIG, title=None),
        encoding="utf-8-sig",
    )

    assert _document_title(html) == "MetaTitle"


def test_document_title_is_html_escaped(tmp_path: Path):
    html = _convert(
        tmp_path,
        "title.md",
        "# Hi\n",
        dict(BASE_CONFIG, title="A <b>B</b>"),
    )

    assert _document_title(html) == "A &lt;b&gt;B&lt;/b&gt;"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="known: TOC text is re-interpreted as HTML",
)
def test_toc_text_matches_the_body_heading_for_plain_text(tmp_path: Path):
    html = _convert(tmp_path, "lt.md", "# a < b\n", dict(BASE_CONFIG, title=None))

    assert _toc_title(html) == _body_heading_title(html)


def test_toc_text_matches_the_body_heading_for_raw_html(tmp_path: Path):
    html = _convert(tmp_path, "raw.md", "# a <b>x</b> y\n", dict(BASE_CONFIG, title=None))

    assert _toc_title(html) == _body_heading_title(html)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="known: overwrite=False is ignored",
)
def test_existing_output_is_preserved_when_overwrite_is_false(tmp_path: Path):
    source = tmp_path / "keep.md"
    source.write_text("# New\n", encoding="utf-8")
    output = tmp_path / "keep.html"
    output.write_text("SENTINEL", encoding="utf-8")

    converter.process_single(str(source), str(output), dict(BASE_CONFIG, overwrite=False))

    assert output.read_text(encoding="utf-8") == "SENTINEL"


@pytest.mark.xfail(
    strict=True,
    raises=ExpectedRenderFailure,
    reason="known: process_batch aborts on the first failure",
)
def test_batch_continues_when_a_single_document_fails(tmp_path: Path, monkeypatch):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    broken = source_dir / "a.md"
    healthy = source_dir / "b.md"
    broken.write_text("# BOOM\n", encoding="utf-8")
    healthy.write_text("# Fine\n", encoding="utf-8")

    def fake_render(md_text, context=None):
        if "BOOM" in md_text:
            raise ExpectedRenderFailure("simulated renderer failure")
        return {"html": "<p>rendered</p>", "headings": [], "assets": {}, "warnings": []}

    monkeypatch.setattr(converter, "render_markdown_node", fake_render)

    output_dir = tmp_path / "out"
    inputs = [str(broken), str(healthy)]
    plan = build_conversion_plan(inputs, str(output_dir))
    converter.process_batch(inputs, str(output_dir), BASE_CONFIG, plan=plan)

    assert (output_dir / "b.html").exists()
