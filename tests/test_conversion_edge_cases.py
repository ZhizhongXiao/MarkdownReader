"""Regression contracts for conversion edge cases.

The tests marked xfail(strict=True) document known defects that are scheduled
for a later fix. The strict marker makes the suite fail once the behaviour is
corrected, which forces the marker to be removed in the fixing commit.
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


def _convert(tmp_path: Path, name: str, text: str, cfg: dict, encoding: str = "utf-8") -> str:
    """Convert one Markdown file and return the generated HTML."""
    source = tmp_path / name
    source.write_text(text, encoding=encoding)
    output = tmp_path / (source.stem + ".html")
    assert converter.process_single(str(source), str(output), cfg) is not None
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


@pytest.mark.xfail(strict=True, reason="known: UTF-8 BOM defeats front matter detection")
def test_front_matter_is_read_when_the_file_starts_with_a_bom(tmp_path: Path):
    html = _convert(
        tmp_path,
        "bom.md",
        "---\ntitle: MetaTitle\n---\n\n# Body\n",
        dict(BASE_CONFIG, title=None),
        encoding="utf-8-sig",
    )

    assert _document_title(html) == "MetaTitle"


@pytest.mark.xfail(strict=True, reason="known: title is not HTML-escaped")
def test_document_title_is_html_escaped(tmp_path: Path):
    html = _convert(
        tmp_path,
        "title.md",
        "# Hi\n",
        dict(BASE_CONFIG, title="A <b>B</b>"),
    )

    assert _document_title(html) == "A &lt;b&gt;B&lt;/b&gt;"


@pytest.mark.xfail(strict=True, reason="known: TOC text is re-interpreted as HTML")
def test_toc_does_not_reinterpret_plain_text_as_html(tmp_path: Path):
    html = _convert(tmp_path, "lt.md", "# a < b\n", dict(BASE_CONFIG, title=None))

    assert _toc_title(html) == "a &lt; b"


def test_toc_keeps_raw_html_that_markdown_allows(tmp_path: Path):
    html = _convert(tmp_path, "raw.md", "# a <b>x</b> y\n", dict(BASE_CONFIG, title=None))

    assert _toc_title(html) == "a <b>x</b> y"


@pytest.mark.xfail(strict=True, reason="known: overwrite=False is ignored")
def test_existing_output_is_preserved_when_overwrite_is_false(tmp_path: Path):
    source = tmp_path / "keep.md"
    source.write_text("# New\n", encoding="utf-8")
    output = tmp_path / "keep.html"
    output.write_text("SENTINEL", encoding="utf-8")

    converter.process_single(str(source), str(output), dict(BASE_CONFIG, overwrite=False))

    assert output.read_text(encoding="utf-8") == "SENTINEL"


@pytest.mark.xfail(strict=True, reason="known: process_batch aborts on the first failure")
def test_batch_continues_when_a_single_document_fails(tmp_path: Path, monkeypatch):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    broken = source_dir / "a.md"
    healthy = source_dir / "b.md"
    broken.write_text("# BOOM\n", encoding="utf-8")
    healthy.write_text("# Fine\n", encoding="utf-8")

    real_render = converter.render_markdown_node

    def fake_render(md_text, context=None):
        if "BOOM" in md_text:
            raise RuntimeError("boom")
        return real_render(md_text, context=context)

    monkeypatch.setattr(converter, "render_markdown_node", fake_render)

    output_dir = tmp_path / "out"
    inputs = [str(broken), str(healthy)]
    plan = build_conversion_plan(inputs, str(output_dir))
    converter.process_batch(inputs, str(output_dir), BASE_CONFIG, plan=plan)

    assert (output_dir / "b.html").exists()
