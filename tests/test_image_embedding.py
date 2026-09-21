"""Local Markdown image embedding contract.

Stage 5 embeds standard Markdown images that resolve to local files as data URIs.
Everything else keeps the source document semantics: remote and unknown schemes
stay untouched, and an unreadable local file keeps its original reference plus a
warning instead of failing the document.

Each behaviour is locked separately, so a partial implementation turns exactly
the finished cases green.
"""

import base64
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.renderer_node import render_markdown_node  # noqa: E402

# Minimal 1x1 PNG written to tmp_path so local image references resolve.
_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)

_PNG_PREFIX = "data:image/png;base64,"
_PNG_BASE64 = base64.b64encode(_MINIMAL_PNG).decode("ascii")


def _context(tmp_path: Path, source_name: str = "doc.md") -> dict:
    return {
        "source_path": str(tmp_path / source_name),
        "output_path": str(tmp_path / "out" / "doc.html"),
        "document_map": {},
    }


def _render(markdown: str, tmp_path: Path) -> dict:
    """Render one document with a source path that local images resolve against."""
    return render_markdown_node(markdown, context=_context(tmp_path))


def _img_src(html: str) -> str:
    """Return the src attribute of the first img element."""
    match = re.search(r'<img[^>]*\bsrc="([^"]*)"', html)
    assert match, html
    return match.group(1)


def _payload(src: str) -> bytes:
    """Decode the base64 payload of a data URI, ignoring URL re-encoding."""
    return base64.b64decode(src.split(",", 1)[1], validate=False)


def _embedded(src: str) -> bool:
    """Return whether the src is an embedded PNG carrying the fixture bytes."""
    if not src.startswith(_PNG_PREFIX):
        return False
    try:
        return _payload(src) == _MINIMAL_PNG
    except Exception:
        return False


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="known: local Markdown images are not embedded yet")
def test_relative_local_image_is_embedded(tmp_path: Path):
    (tmp_path / "pic.png").write_bytes(_MINIMAL_PNG)

    result = _render("![a](pic.png)", tmp_path)

    assert _embedded(_img_src(result["html"]))


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="known: local Markdown images are not embedded yet")
def test_absolute_local_image_is_embedded(tmp_path: Path):
    image = tmp_path / "pic.png"
    image.write_bytes(_MINIMAL_PNG)

    result = _render("![a](" + image.as_posix() + ")", tmp_path)

    assert _embedded(_img_src(result["html"]))


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="known: local Markdown images are not embedded yet")
def test_image_path_with_spaces_and_unicode_is_embedded(tmp_path: Path):
    (tmp_path / "图片 one.png").write_bytes(_MINIMAL_PNG)

    result = _render("![a](<图片 one.png>)", tmp_path)

    assert _embedded(_img_src(result["html"]))


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="known: local file URIs are not embedded yet")
def test_local_file_uri_is_embedded(tmp_path: Path):
    image = tmp_path / "pic.png"
    image.write_bytes(_MINIMAL_PNG)

    result = _render("![a](" + image.as_uri() + ")", tmp_path)

    assert _embedded(_img_src(result["html"]))


def test_existing_data_uri_is_left_untouched(tmp_path: Path):
    uri = _PNG_PREFIX + _PNG_BASE64

    result = _render("![a](" + uri + ")", tmp_path)

    src = _img_src(result["html"])
    assert src.startswith(_PNG_PREFIX)
    assert _payload(src) == _MINIMAL_PNG


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="known: local Markdown images are not embedded yet")
def test_image_inside_a_link_is_embedded_but_the_link_is_kept(tmp_path: Path):
    (tmp_path / "pic.png").write_bytes(_MINIMAL_PNG)

    result = _render("[![a](pic.png)](https://example.com)", tmp_path)
    html = result["html"]

    assert 'href="https://example.com"' in html
    assert _embedded(_img_src(html))

@pytest.mark.xfail(strict=True, raises=AssertionError, reason="known: local Markdown images are not embedded yet")
def test_repeated_references_are_all_embedded(tmp_path: Path):
    (tmp_path / "pic.png").write_bytes(_MINIMAL_PNG)

    result = _render("![a](pic.png) and ![b](pic.png)", tmp_path)
    sources = re.findall(r'<img[^>]*\bsrc="([^"]*)"', result["html"])

    assert len(sources) == 2
    assert all(_embedded(src) for src in sources)


def test_toc_heading_keeps_alt_text_for_an_image(tmp_path: Path):
    (tmp_path / "pic.png").write_bytes(_MINIMAL_PNG)

    headings = _render("# ![alt](pic.png)", tmp_path)["headings"]

    assert headings[0]["toc_inline_html"] == "alt"
    assert "data:" not in headings[0]["toc_inline_html"]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="known: missing images do not warn yet")
def test_missing_local_image_keeps_src_and_warns(tmp_path: Path):
    result = _render("![a](missing.png)", tmp_path)

    assert _img_src(result["html"]) == "missing.png"
    assert result["warnings"]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="known: host file URIs do not warn yet")
def test_host_style_file_uri_keeps_src_and_warns(tmp_path: Path):
    result = _render("![a](file://host/share/pic.png)", tmp_path)

    assert _img_src(result["html"]) == "file://host/share/pic.png"
    assert result["warnings"]


def test_remote_image_is_left_untouched(tmp_path: Path):
    sources = [
        "http://example.com/a.png",
        "https://example.com/a.png",
        "//cdn.example.com/a.png",
    ]
    for source in sources:
        result = _render("![a](" + source + ")", tmp_path)

        assert _img_src(result["html"]) == source
        assert result["warnings"] == []


def test_source_image_file_is_not_modified(tmp_path: Path):
    image = tmp_path / "pic.png"
    image.write_bytes(_MINIMAL_PNG)
    before = image.read_bytes()

    _render("![a](pic.png)", tmp_path)

    assert image.read_bytes() == before