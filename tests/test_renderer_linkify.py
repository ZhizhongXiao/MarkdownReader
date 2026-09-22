"""Bare file names must stay text; real URLs and explicit links keep working.

A Markdown reader meets bare file names far more often than scheme less domains: a
document that says README.md, report.md or 版本 1.2.3 is naming files, not hosts.
markdown-it linkify does the opposite by default and mints http links with punycode
hosts, because file extensions such as .md are also country codes.
"""

from pathlib import Path

from core.renderer_node import render_markdown_node


def _context(source: Path, output: Path, mapping=None) -> dict:
    return {
        "source_path": str(source),
        "output_path": str(output),
        "document_map": {str(key): str(value) for key, value in (mapping or {}).items()},
    }


def _render(markdown: str, tmp_path: Path, mapping=None) -> str:
    source = tmp_path / "doc.md"
    source.write_text("", encoding="utf-8")
    return render_markdown_node(markdown, context=_context(source, tmp_path / "doc.html", mapping))[
        "html"
    ]


def test_a_bare_file_name_is_not_turned_into_a_domain(tmp_path: Path):
    html = _render("见 根文档.md 与 README.md 与 report.md 与版本 1.2.3。", tmp_path)
    assert "根文档.md" in html
    assert "README.md" in html
    assert "report.md" in html
    assert 'href="http:' not in html, "a file name must not become an http link"


def test_a_bare_name_is_not_partly_linked(tmp_path: Path):
    html = _render("见 乙组/YAML 全类型.md。", tmp_path)
    assert "乙组/YAML 全类型.md" in html
    assert "全类型.md</a>" not in html, "the tail of a path must not be linked"


def test_a_real_url_is_still_linkified(tmp_path: Path):
    html = _render("访问 https://example.com 与 mailto:qa@example.com。", tmp_path)
    assert 'href="https://example.com"' in html
    assert 'href="mailto:qa@example.com"' in html


def test_an_explicit_markdown_link_is_still_rewritten(tmp_path: Path):
    source = tmp_path / "根文档.md"
    target = tmp_path / "中文 空格 目录" / "文档 一.md"
    target.parent.mkdir()
    source.write_text("", encoding="utf-8")
    target.write_text("", encoding="utf-8")
    target_output = tmp_path / "中文 空格 目录" / "文档 一.html"

    html = _render(
        "[空格文档](<中文 空格 目录/文档 一.md>)",
        tmp_path,
        {target: target_output},
    )
    assert ".md" not in html, "an explicit Markdown link must still be rewritten"
    assert "%E6%96%87%E6%A1%A3" in html
