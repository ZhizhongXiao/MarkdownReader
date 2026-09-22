"""Structural contracts for the generated demo document.

These assertions replace the old hand-maintained samples/expected/demo.html
snapshot: they describe the structure the demo must have without pinning the
whole HTML, so styling tweaks no longer require refreshing a large fixture.
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
