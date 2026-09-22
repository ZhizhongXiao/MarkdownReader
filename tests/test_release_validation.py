"""Release validation facts that do not need a packaged build.

The end to end EXE smoke test lives in packaging/validate_release.py, but these
cases lock the parts of the release contract that can be checked in process: the
runtime prefers the Node the package carries, and a conversion lands correctly in
a directory whose name has Chinese characters and spaces, which is what a
localized Windows profile actually looks like.
"""

import pytest

from core import renderer_node

CONFIG = {"template": "modern", "numbering": True, "overwrite": True}


@pytest.fixture(autouse=True)
def _fresh_runtime_cache(monkeypatch):
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE", None)


def test_the_bundled_runtime_wins_even_when_frozen(monkeypatch, tmp_path):
    bundled = tmp_path / "node" / "node.exe"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    bundled.write_bytes(b"stub")
    monkeypatch.setattr(renderer_node, "_BUNDLED_NODE", str(bundled))
    monkeypatch.setattr(renderer_node, "_is_frozen", lambda: True)
    assert renderer_node.resolve_node_runtime() == str(bundled)


def test_a_conversion_survives_a_chinese_path_with_spaces(tmp_path):
    from core import converter

    directory = tmp_path / "中文 目录" / "输出 结果"
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "笔记 一.md"
    source.write_text("# 标题\n\n正文。\n", encoding="utf-8")
    target = directory / "笔记 一.html"

    result = converter.process_single(str(source), str(target), CONFIG)
    assert result is not None, "a localized path must not stop the conversion"
    assert target.is_file()
    assert "标题" in target.read_text(encoding="utf-8")


def test_the_renderer_runs_from_a_path_with_spaces(tmp_path):
    from core import converter

    directory = tmp_path / "目录 with spaces"
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "a.md"
    source.write_text("# 标题\n\n`code`\n", encoding="utf-8")
    result = converter.process_single(str(source), str(directory / "a.html"), CONFIG)
    assert result is not None
    assert (directory / "a.html").is_file()
