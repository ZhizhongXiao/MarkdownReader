"""The retired v1 path cannot be selected by production callers."""

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import converter, renderer_node  # noqa: E402
from core.config import PRODUCTION_RENDERER_VERSION  # noqa: E402

CONFIG = {"template": "modern", "overwrite": True}


def test_the_renderer_identity_is_v2():
    assert PRODUCTION_RENDERER_VERSION == "v2"


def test_production_entrypoints_have_no_renderer_version_selector():
    for function in (
        converter.process_single,
        converter.process_batch,
        renderer_node.render_markdown_node,
    ):
        assert "renderer_version" not in inspect.signature(function).parameters


def test_the_converter_always_assembles_through_the_supported_path(tmp_path, monkeypatch):
    seen = []
    original = converter.assemble_document

    def counting(*args, **kwargs):
        seen.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(converter, "assemble_document", counting)
    source = tmp_path / "doc.md"
    source.write_text("# 标题\n\n公式 $a^2$。\n", encoding="utf-8")
    output = tmp_path / "doc.html"

    saved = converter.process_single(str(source), str(output), dict(CONFIG))

    assert saved == str(output)
    assert seen == [True]
    html = output.read_text(encoding="utf-8")
    assert 'class="katex"' in html
    assert "KaTeX_AMS" in html
