"""Structural contracts for the generated demo document.

samples/demo.md is the specimen of what the reader supports, and samples/demo.html
is committed next to it, so a fresh render has to match the repository copy: a
drift in the renderer, the templates or the demo source surfaces here instead of
being reviewed away. The structural assertions describe landmarks the demo must
keep, and the snapshot contract locks the rest.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.generate_demo import generate_demo  # noqa: E402


@pytest.fixture(scope="module")
def demo_html(tmp_path_factory) -> str:
    """Generate the demo document once and return its markup."""
    output = tmp_path_factory.mktemp("demo") / "demo.html"
    generate_demo(output=output)
    return output.read_text(encoding="utf-8")


def test_demo_generation_writes_a_standalone_document(demo_html: str):
    assert "<html" in demo_html
    assert "<body" in demo_html


def test_demo_uses_the_modern_theme_body_class(demo_html: str):
    assert 'class="theme-modern"' in demo_html


def test_demo_contains_flat_toc_rows(demo_html: str):
    assert 'class="toc-row"' in demo_html


def test_demo_has_no_legacy_nested_toc_markup(demo_html: str):
    assert "toc-item" not in demo_html
    assert "toc-list" not in demo_html


def test_demo_inlines_katex_assets(demo_html: str):
    """samples/demo.md contains real formulas, so the fonts must be present."""
    assert 'class="katex"' in demo_html
    assert "KaTeX_AMS" in demo_html


def test_demo_inlines_the_shared_viewer_javascript(demo_html: str):
    assert "markdownreader-theme" in demo_html
    assert "function applyTheme" in demo_html


def test_demo_html_matches_the_committed_specimen(tmp_path: Path):
    """A fresh render must equal samples/demo.html byte for byte, modulo newlines.

    The committed page is the artifact readers open, so it is only useful as a
    specimen while it is exactly what the current sources produce.
    """
    generated = tmp_path / "demo.html"
    generate_demo(output=generated)

    committed = ROOT / "samples" / "demo.html"
    expected = committed.read_text(encoding="utf-8").replace("\r\n", "\n")
    actual = generated.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert actual == expected, (
        "samples/demo.html no longer matches the sources: run "
        "`python tools/generate_demo.py` and commit the regenerated file "
        "(or fix what changed in templates/, node_renderer/ or samples/demo.md)."
    )
