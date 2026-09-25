"""Cutover C4：production renderer policy 与回退路径。

production 默认现在是 v2（`core.config.PRODUCTION_RENDERER_VERSION`），v1 保留为显式回退。
这里锁三件事：policy 是单一来源、默认路径真的 dispatch 到 v2 装配、显式 v1 仍可用。

默认选项里 `fetch_remote_resources` 是开启的（生产默认），因此本套件的 Markdown 一律不含
远程引用，等价于不联网。
"""

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import converter, renderer_node  # noqa: E402
from core.config import PRODUCTION_RENDERER_VERSION  # noqa: E402

CONFIG = {"template": "modern", "overwrite": True}


def test_the_production_policy_is_v2():
    assert PRODUCTION_RENDERER_VERSION == "v2", (
        "C4 的 cutover 点：回退只需把 core/config.py 里这一行改回 'v1' 并重建"
    )


def test_the_converter_defaults_to_the_policy():
    """converter 是 production consumer：默认值必须引用 policy，而不是另写一个字面量。"""
    for function in (converter.process_single, converter.process_batch):
        default = inspect.signature(function).parameters["renderer_version"].default
        assert default == PRODUCTION_RENDERER_VERSION, function.__name__


def test_the_bridge_keeps_its_own_v1_default():
    """`render_markdown_node` 是低层 bridge，不是 policy 持有者（C2 的边界）。"""
    default = inspect.signature(renderer_node.render_markdown_node).parameters[
        "renderer_version"
    ].default
    assert default == "v1"


def test_startup_validation_follows_the_policy(monkeypatch):
    """frozen 启动检查必须验证 production renderer，而不是只验 v1。"""
    calls = []
    monkeypatch.setattr(
        renderer_node, "validate_renderer_runtime", lambda: calls.append("v1") or "node"
    )
    monkeypatch.setattr(renderer_node, "_require_v2_runtime", lambda: calls.append("v2") or "node")

    renderer_node.validate_renderer_runtime_for(PRODUCTION_RENDERER_VERSION)

    assert calls == ["v2"], calls


def test_the_default_conversion_assembles_through_the_v2_path(tmp_path, monkeypatch):
    """不传 renderer_version 时必须走 v2 装配，而不是悄悄留在 v1。"""
    seen = {}
    original = converter.assemble_document

    def counting(*args, **kwargs):
        seen["called"] = True
        return original(*args, **kwargs)

    monkeypatch.setattr(converter, "assemble_document", counting)

    source = tmp_path / "doc.md"
    source.write_text("# 标题\n\n公式 $a^2$。\n", encoding="utf-8")
    output = tmp_path / "doc.html"
    report: dict = {}

    saved = converter.process_single(str(source), str(output), dict(CONFIG), report=report)

    assert saved == str(output)
    assert seen.get("called"), "默认路径必须经过 core/html_assembly.py"
    html = output.read_text(encoding="utf-8")
    assert 'class="katex"' in html
    assert "KaTeX_AMS" in html, "v2 的 KaTeX 载荷来自 resources.styles"


def test_an_explicit_v1_conversion_still_works(tmp_path):
    """回退证明：显式 v1 仍产出等价文档（只是载荷通道不同）。"""
    source = tmp_path / "doc.md"
    source.write_text("# 标题\n\n公式 $a^2$。\n", encoding="utf-8")
    output = tmp_path / "doc.html"
    report: dict = {}

    saved = converter.process_single(
        str(source),
        str(output),
        dict(CONFIG),
        report=report,
        renderer_version="v1",
    )

    assert saved == str(output)
    html = output.read_text(encoding="utf-8")
    assert 'class="katex"' in html
    assert "KaTeX_AMS" in html, "v1 的 KaTeX 载荷仍走 assets.css"


def test_an_unknown_renderer_version_is_refused(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("# 标题\n", encoding="utf-8")

    with pytest.raises(ValueError):
        converter.process_single(
            str(source),
            str(tmp_path / "doc.html"),
            dict(CONFIG),
            renderer_version="v3",
        )
