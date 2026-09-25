"""Release validation facts that do not need a packaged build.

The end to end EXE smoke test lives in packaging/validate_release.py, but these
cases lock the parts of the release contract that can be checked in process: the
runtime prefers the Node the package carries, a conversion lands correctly in a
directory whose name has Chinese characters and spaces (what a localized Windows
profile actually looks like), and the packaged payload carries both renderers.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import renderer_node  # noqa: E402

CONFIG = {"template": "modern", "numbering": True, "overwrite": True}


def _load_validation_module():
    """Import packaging/validate_release.py by path: `packaging` is also a PyPI name."""
    spec = importlib.util.spec_from_file_location(
        "validate_release_under_test", ROOT / "packaging" / "validate_release.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_release = _load_validation_module()


def test_the_release_payload_carries_both_renderers():
    """v2 是 production 载荷，v1 的脚本与依赖继续随包发布（回退路径）。"""
    files = validate_release.RUNTIME_FILES

    assert ("renderer", "dist", "renderer.cjs") in files
    assert ("renderer", "dist", "katex") in files
    assert ("renderer", "dist", "mermaid") in files
    assert ("node", "node.exe") in files, "内置 Node 也是 v2 renderer 的运行时"
    assert ("node_renderer", "render.js") in files, "v1 回退路径必须继续随包发布"
    assert ("node_renderer", "node_modules") in files


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
