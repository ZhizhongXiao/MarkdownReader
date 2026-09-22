from pathlib import Path

from core.renderer_node import render_markdown_node


def _context(source: Path, output: Path, mapping: dict[Path, Path]) -> dict:
    return {
        "source_path": str(source),
        "output_path": str(output),
        "document_map": {str(key): str(value) for key, value in mapping.items()},
    }


def test_footnote_link_is_rendered_and_known_markdown_target_is_rewritten(tmp_path: Path):
    source = tmp_path / "第24章.md"
    target = tmp_path / "第20章 非货币性资产交换.md"
    source.write_text("", encoding="utf-8")
    target.write_text("", encoding="utf-8")
    source_output = tmp_path / "html" / "第24章.html"
    target_output = tmp_path / "html" / "第20章 非货币性资产交换.html"

    markdown = (
        "计量方法[^chapter]\n\n"
        "[^chapter]: 参见[第20章](<./第20章 非货币性资产交换.md#第二节>)。"
    )
    result = render_markdown_node(
        markdown,
        context=_context(source, source_output, {source: source_output, target: target_output}),
    )

    assert 'class="footnote-ref"' in result["html"]
    assert 'class="footnotes"' in result["html"]
    assert "%E7%AC%AC20%E7%AB%A0" in result["html"]
    assert ".html#%E7%AC%AC%E4%BA%8C%E8%8A%82" in result["html"]
    assert "[^chapter]" not in result["html"]
    assert result["warnings"] == []


def test_unselected_markdown_target_is_left_unchanged_with_warning(tmp_path: Path):
    source = tmp_path / "第24章.md"
    source.write_text("", encoding="utf-8")
    source_output = tmp_path / "html" / "第24章.html"

    result = render_markdown_node(
        "[未选择章节](./第7章.md)",
        context=_context(source, source_output, {source: source_output}),
    )

    assert ".md" in result["html"]
    assert any("未加入转换清单" in warning for warning in result["warnings"])
    warning = next(w for w in result["warnings"] if "未加入转换清单" in w)
    assert "./第7章.md" in warning, "the message must read like the document writes it"
    assert "%E7" not in warning


def test_internal_and_external_links_are_not_rewritten(tmp_path: Path):
    source = tmp_path / "第24章.md"
    output = tmp_path / "第24章.html"
    source.write_text("", encoding="utf-8")

    result = render_markdown_node(
        "[本节](#section) [网站](https://example.com) [旧HTML](./第20章.html)",
        context=_context(source, output, {source: output}),
    )

    assert 'href="#section"' in result["html"]
    assert 'href="https://example.com"' in result["html"]
    assert "%E7%AC%AC20%E7%AB%A0.html" in result["html"]
    assert result["warnings"] == []

def test_heading_link_warning_is_reported_once(tmp_path: Path):
    """A heading link warns once, not once per internal render pass."""
    source = tmp_path / "第24章.md"
    source.write_text("", encoding="utf-8")
    source_output = tmp_path / "html" / "第24章.html"

    result = render_markdown_node(
        "# 参见[未选择章节](./missing.md)",
        context=_context(source, source_output, {source: source_output}),
    )

    assert sum("未加入转换清单" in warning for warning in result["warnings"]) == 1


def _unlisted_warning(tmp_path: Path, markdown: str) -> str:
    """Return the single warning about a target that is not in the conversion plan."""
    source = tmp_path / "第24章.md"
    source.write_text("", encoding="utf-8")
    output = tmp_path / "html" / "第24章.html"
    result = render_markdown_node(markdown, context=_context(source, output, {source: output}))

    warnings = [warning for warning in result["warnings"] if "未加入转换清单" in warning]
    assert len(warnings) == 1, result["warnings"]
    return warnings[0]


def test_an_unlisted_warning_keeps_the_query_and_the_fragment(tmp_path: Path):
    """The whole address is decoded, not only its path part."""
    warning = _unlisted_warning(tmp_path, "[章节](./章节.md?view=1#第二节)")

    assert "./章节.md?view=1#第二节" in warning


def test_an_unlisted_warning_shows_a_percent_file_name_as_written(tmp_path: Path):
    """100%.md travels as 100%25.md; the message has to show the real name."""
    warning = _unlisted_warning(tmp_path, "[百分号](./100%.md)")

    assert "./100%.md" in warning


def test_an_unlisted_warning_survives_a_malformed_percent_sequence(tmp_path: Path):
    """An address that cannot be decoded is reported unchanged, without raising."""
    warning = _unlisted_warning(tmp_path, "[坏编码](./broken%E0%A4%A.md)")

    # markdown-it itself rewrites the stray %A as %25A, and %E0%A4 is an
    # incomplete UTF-8 sequence, so there is nothing to decode here. The raw text
    # is what the author has to see.
    assert "./broken%E0%A4%25A.md" in warning
