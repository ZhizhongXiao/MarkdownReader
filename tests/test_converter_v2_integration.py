"""Cutover C3：converter 的显式 v2 装配路径（K26）。

这边测的是**接线**，不是 renderer 语义：`process_single(renderer_version="v2")` 必须把
v2 envelope 交给 `core/html_assembly.py`，把 v1 的 warning 语义保留下来，并且**不改变默认路径**。

closure checker 只在测试里跑（`tools/standalone_closure.py`）；`core/converter.py` 运行期不得引用它
（由 `test_the_runtime_converter_does_not_reference_the_closure_checker` 锁住）。
默认离线：`renderer_options={"fetch_remote_resources": False}`，不访问公共网络。
"""

import base64
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer_adapter import require_node  # noqa: E402
from standalone_closure import author_refs_from_envelope  # noqa: E402

from core import converter, renderer_v2  # noqa: E402
from core.html_assembly import assemble_document  # noqa: E402
from core.renderer_node import render_markdown_node  # noqa: E402
from tools.standalone_closure import scan  # noqa: E402

# 与 tests/test_renderer_adapter_resources.py 一致的 1x1 PNG。
MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
CONFIG = {
    "template": "modern",
    "title": "v2 集成文档",
    "build_index": False,
    "auto_open": False,
}
OFFLINE = {"fetch_remote_resources": False}
FONT_DATA_URI_MARKER = "url(data:font/woff2;base64,"
FONT_FAMILY_MARKER = "KaTeX_AMS"
MERMAID_BOOT_MARKER = "window.mermaid.initialize"


@pytest.fixture(autouse=True)
def _fresh_v2_runtime(monkeypatch):
    """每个用例都从「v2 运行时未验证」开始，并确保 Node 可用。"""
    require_node()
    monkeypatch.setattr(renderer_v2, "_VALIDATED_RUNTIME", None)


def write_png(directory: Path, name: str = "pic.png") -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MINIMAL_PNG)
    return path


def convert(
    tmp_path: Path,
    markdown: str,
    *,
    name: str = "doc.md",
    output: Path | None = None,
    options: dict | None = None,
    cfg: dict | None = None,
    link_context: dict | None = None,
    version: str | None = "v2",
) -> dict:
    """Run the production converter and return the artefacts for assertions."""
    source = tmp_path / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(markdown, encoding="utf-8")
    output = output or source.with_suffix(".html")
    report: dict = {}
    resolved_options = OFFLINE if options is None else options
    if version != "v2":
        resolved_options = None  # v1 拒绝非空 options
    kwargs = {} if version is None else {"renderer_version": version}
    saved = converter.process_single(
        str(source),
        str(output),
        dict(CONFIG, **(cfg or {})),
        link_context=link_context,
        report=report,
        renderer_options=resolved_options,
        **kwargs,
    )
    return {
        "saved": saved,
        "source": source,
        "output": output,
        "html": output.read_text(encoding="utf-8") if output.is_file() else None,
        "report": report,
    }


def envelope_for(markdown: str, context: dict, options: dict | None = None) -> dict:
    """Render the same input directly, so the closure checker can be fed in tests."""
    return render_markdown_node(
        markdown,
        context=context,
        renderer_version="v2",
        options=dict(OFFLINE, **(options or {})),
    )


def test_a_plain_document_is_assembled_from_the_v2_envelope(tmp_path):
    result = convert(tmp_path, "# 标题\n\n普通文本。\n")

    html = result["html"]
    assert result["saved"] == str(result["output"])
    assert "theme-modern" in html, "assembler 必须写主题 body class"
    assert "<h1" in html and "普通文本。" in html
    assert "v2 集成文档" in html, "占位符必须被标题填满"
    assert FONT_FAMILY_MARKER not in html, "K21：没有公式就不带 KaTeX 载荷"
    assert "mermaid" not in html, "K22：没有 Mermaid 就不带 runtime"
    assert scan(html)["verdict"] == "standalone"


def test_a_formula_delivers_the_katex_payload(tmp_path):
    result = convert(tmp_path, "# 标题\n\n公式 $a^2+b^2=c^2$。\n")

    html = result["html"]
    assert 'class="katex"' in html
    assert FONT_FAMILY_MARKER in html
    assert FONT_DATA_URI_MARKER in html, "字体必须是 data URI（standalone）"
    assert scan(html)["verdict"] == "standalone"


def test_a_mermaid_fence_delivers_the_runtime_and_boot(tmp_path):
    result = convert(tmp_path, "# 标题\n\n```mermaid\ngraph TD; A-->B;\n```\n")

    html = result["html"]
    assert 'class="mermaid"' in html and "graph TD" in html
    assert MERMAID_BOOT_MARKER in html, "resources.scripts 的 runtime + boot 必须真的注入"
    assert scan(html)["verdict"] == "standalone"


def test_a_local_image_is_embedded(tmp_path):
    write_png(tmp_path)

    result = convert(tmp_path, "# 标题\n\n![图](pic.png)\n")

    assert "data:image/png;base64," in result["html"]
    assert scan(result["html"])["verdict"] == "standalone"


def test_cross_document_markdown_links_still_rewrite_to_html(tmp_path):
    target = tmp_path / "第20章.md"
    target.write_text("# 第二十章\n", encoding="utf-8")
    output = tmp_path / "html" / "第24章.html"

    result = convert(
        tmp_path,
        "参见[第20章](./第20章.md)。\n",
        name="第24章.md",
        output=output,
        link_context={
            "source_path": str(tmp_path / "第24章.md"),
            "output_path": str(output),
            "document_map": {
                str(tmp_path / "第24章.md"): str(output),
                str(target): str(tmp_path / "html" / "第20章.html"),
            },
        },
    )

    assert result["saved"] == str(output)
    assert "第20章.md" not in result["html"], "Markdown 链接必须被重写成 .html"
    # 重写后的 href 与 4B 契约一致：百分号编码（见 tests/test_renderer_links.py）。
    assert "%E7%AC%AC20%E7%AB%A0.html" in result["html"]


def test_a_remote_image_kept_offline_is_reported_as_degraded_not_failure(tmp_path):
    """离线时 remote 只 kept（5C）：URL 原样保留、不报 warning，但 closure 是 degraded。"""
    markdown = "![图](https://kept.invalid/a.png)\n"
    result = convert(tmp_path, markdown)

    assert "https://kept.invalid/a.png" in result["html"], "原 URL 必须保留"
    assert result["report"]["warnings"] == [], "kept 不产生 warning"
    envelope = envelope_for(
        markdown,
        {"source_path": str(result["source"]), "output_path": str(result["output"])},
    )
    report = scan(result["html"], envelope=envelope)
    assert report["verdict"] == "degraded", report["problems"]


def test_author_raw_html_is_preserved_and_reported_as_provenance(tmp_path):
    markdown = '<img src="https://raw.invalid/a.png">\n'
    result = convert(tmp_path, markdown)

    assert 'src="https://raw.invalid/a.png"' in result["html"], "作者 HTML 不得被改写"
    assert result["report"]["warnings"] == []
    envelope = envelope_for(
        markdown,
        {"source_path": str(result["source"]), "output_path": str(result["output"])},
    )
    assert author_refs_from_envelope(envelope) == [
        {"ref": "https://raw.invalid/a.png", "count": 1}
    ]
    assert scan(result["html"], envelope=envelope)["verdict"] == "author_references"


def test_numbering_is_injected_when_enabled(tmp_path):
    result = convert(tmp_path, "# 标题\n\n## 小节\n", cfg={"numbering": True})
    plain = convert(tmp_path, "# 标题\n\n## 小节\n", name="plain.md", cfg={"numbering": False})

    assert "btn-auto-numbering" in result["html"]
    assert result["html"].count("btn-auto-numbering") > plain["html"].count("btn-auto-numbering")


def test_renderer_warnings_come_before_assembly_warnings(tmp_path, monkeypatch):
    """warnings 合并顺序是契约：renderer（网络/资源）在前，assembly（模板降级）在后。"""
    monkeypatch.setattr(
        converter,
        "render_markdown_node",
        lambda *args, **kwargs: {"html": "<p>x</p>", "headings": [], "warnings": ["渲染降级"]},
    )
    monkeypatch.setattr(
        converter,
        "assemble_document",
        lambda *args, **kwargs: {
            "html": "<html>assembled</html>",
            "injections": [],
            "assembly_warnings": ["模板降级"],
        },
    )

    result = convert(tmp_path, "# 标题\n")

    assert result["report"]["warnings"] == ["渲染降级", "模板降级"]
    assert result["html"] == "<html>assembled</html>"
    assert result["saved"] == str(result["output"])


def test_the_converter_writes_exactly_what_the_assembler_produced(tmp_path):
    """接线锁：converter 不得二次加工 v2 assembler 的结果。"""
    write_png(tmp_path)
    markdown = "# 标题\n\n公式 $a^2$。\n\n![图](pic.png)\n"
    result = convert(tmp_path, markdown)

    envelope = envelope_for(
        markdown,
        {"source_path": str(result["source"]), "output_path": str(result["output"])},
    )
    expected = assemble_document(
        envelope,
        title=CONFIG["title"],
        template_name="modern",
        numbering=False,
    )

    assert result["html"] == expected["html"]


def test_an_unusable_template_returns_none_without_writing(tmp_path):
    """与 v1 同一失败语义：模板不可用时 log + 返回 None，不写文件。"""
    result = convert(tmp_path, "# 标题\n", cfg={"template": "no-such-template"})

    assert result["saved"] is None
    assert result["html"] is None


def test_a_missing_v2_artifact_keeps_its_actionable_error(tmp_path, monkeypatch):
    """K26：v2 构建产物缺失是 actionable failure，不被降级成静默 None。"""
    monkeypatch.setattr(renderer_v2, "ARTIFACT", str(tmp_path / "missing" / "renderer.cjs"))
    source = tmp_path / "doc.md"
    source.write_text("# 标题\n", encoding="utf-8")

    with pytest.raises(RuntimeError) as error:
        converter.process_single(
            str(source),
            str(tmp_path / "doc.html"),
            dict(CONFIG),
            renderer_version="v2",
            renderer_options=OFFLINE,
        )

    assert "npm run build" in str(error.value)


def test_the_default_and_explicit_v1_never_use_the_v2_assembler(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("v1 路径不得调用 v2 assembler")

    monkeypatch.setattr(converter, "assemble_document", forbidden)

    default = convert(tmp_path, "# 标题\n", name="default.md", version=None)
    explicit = convert(tmp_path, "# 标题\n", name="explicit.md", version="v1")

    for result in (default, explicit):
        assert result["saved"] == str(result["output"])
        assert "theme-modern" in result["html"]


def test_the_runtime_converter_does_not_reference_the_closure_checker():
    """Closure checker 是 test/release gate，不是每次转换都跑的 runtime 子系统。"""
    source = (ROOT / "core" / "converter.py").read_text(encoding="utf-8")

    assert "standalone_closure" not in source
    assert "tools." not in source
