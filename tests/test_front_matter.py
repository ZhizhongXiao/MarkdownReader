"""Front matter behaviour: one YAML implementation, on every machine.

PyYAML is a runtime dependency, so front matter means the same thing in a source
checkout and in a packaged build. These cases lock the product promises: a BOM is
ignored, the standard YAML types survive, and malformed YAML is reported without
taking the conversion down.
"""

import logging

from core.fm import parse_front_matter


def test_bom_is_ignored():
    metadata, body = parse_front_matter("\ufeff---\ntitle: 带 BOM\n---\n正文\n")
    assert metadata == {"title": "带 BOM"}
    assert body.strip() == "正文"


def test_standard_yaml_types_survive():
    text = (
        "---\n"
        "title: 引号标题\n"
        "tags:\n"
        "  - a\n"
        "  - b\n"
        "author:\n"
        "  name: 张三\n"
        "  links:\n"
        "    - url: https://example.com\n"
        "      label: 主页\n"
        "published: true\n"
        "draft: null\n"
        "weight: 3\n"
        "summary: |\n"
        "  第一行\n"
        "  第二行\n"
        "---\n"
        "正文\n"
    )
    metadata, body = parse_front_matter(text)
    assert metadata["title"] == "引号标题"
    assert metadata["tags"] == ["a", "b"]
    assert metadata["author"]["name"] == "张三"
    assert metadata["author"]["links"] == [{"url": "https://example.com", "label": "主页"}]
    assert metadata["published"] is True
    assert metadata["draft"] is None
    assert metadata["weight"] == 3
    assert metadata["summary"] == "第一行\n第二行\n"
    assert body.strip() == "正文"


def test_malformed_yaml_warns_instead_of_raising(caplog):
    with caplog.at_level(logging.WARNING):
        metadata, body = parse_front_matter("---\ntitle: [未闭合\n---\n正文\n")
    assert metadata == {}
    assert body.strip() == "正文"
    assert any("Front Matter" in record.getMessage() for record in caplog.records)


def test_text_without_front_matter_is_returned_untouched():
    text = "# 标题\n\n正文\n"
    metadata, body = parse_front_matter(text)
    assert metadata == {}
    assert body == text
