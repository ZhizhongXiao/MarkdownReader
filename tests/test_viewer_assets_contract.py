"""Phase 6A: the reader asset layer is the single owner of Viewer/theme knowledge.

`core/viewer_assets.py` answers "what is a reader document made of, and where do
those files live". Before 6A that knowledge was spread over `core/config.py`, both
assembly paths and the GUI dropdown, so moving one file touched five modules.

The contracts below describe **today's** documents. Phase 6C replaces the
"exactly one theme is injected" half with "every builtin theme is injected exactly
once"; asserting that here would lock behaviour the code does not have yet.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import viewer_assets  # noqa: E402
from core.html_assembly import assemble_document  # noqa: E402

# The selector is the directory name today; the canonical id lives in metadata.
# Phase 6B unifies them under `themes/builtin/<id>/`.
SELECTABLE = ["Modern", "Office", "Vscode"]
CANONICAL_IDS = ["modern", "office", "vscode"]
THEME_MARKERS = {
    "Modern": "--modern-guide-border",
    "Office": "--office-page-bg",
    "Vscode": "--vscode-preview-font",
}

CONSUMERS = ("core/converter.py", "core/html_assembly.py", "gui/api.py")
# Functions that used to be read straight out of `core.config` by every consumer.
MOVED_FROM_CONFIG = {
    "theme_body_class",
    "resolve_template_chain",
    "resolve_template_file",
    "load_theme_chain",
    "get_shared_viewer_js_path",
    "get_shared_print_css_path",
}


def envelope(html: str = "<p>正文</p>") -> dict:
    """A minimal successful v2 envelope; the assembler only reads these channels."""
    return {
        "protocol_version": 2,
        "ok": True,
        "html": html,
        "headings": [],
        "features": {},
        "warnings": [],
        "resources": {"items": [], "styles": [], "scripts": [], "author_references": []},
    }


def imported_from(path: str, module: str) -> set:
    """Return the names one of our modules imports from another."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            names.update(alias.name for alias in node.names)
    return names


def test_the_selectable_registry_is_exactly_the_three_builtins():
    assert viewer_assets.theme_ids() == SELECTABLE


def test_the_base_theme_is_hidden_and_never_selectable():
    """base 提供默认 token，但不是用户可选项 —— 沿用 metadata 的 hidden 约定。"""
    assert viewer_assets.theme_metadata("default")["hidden"] is True
    assert "default" not in viewer_assets.theme_ids()
    assert "default" in viewer_assets.theme_ids(include_hidden=True)


def test_the_index_page_directory_is_not_a_theme():
    """批索引页与主题同一个根目录，但没有 metadata.json，因此不进注册表。"""
    assert "index" not in viewer_assets.theme_ids()
    assert viewer_assets.theme_metadata("index") == {}


def test_the_canonical_ids_match_the_registry():
    ids = [viewer_assets.theme_metadata(name).get("id") for name in SELECTABLE]

    assert ids == CANONICAL_IDS


@pytest.mark.parametrize("theme", SELECTABLE)
def test_a_current_document_injects_the_selected_theme_exactly_once(theme):
    """今天每份文档只内嵌所选主题，各通道恰好一次（6C 才内嵌全部 builtin）。"""
    assembled = assemble_document(envelope(), title="标题", template_name=theme)
    labels = [entry["label"] for entry in assembled["injections"]]

    assert labels.count("viewer-css") == 1
    assert labels.count("theme") == 1
    assert labels.count("print") == 1
    assert labels.count("viewer-js") == 1
    assert f'<body class="theme-{theme.lower()}">' in assembled["html"]


def test_an_unselected_theme_does_not_reach_the_document():
    """选 Office 时不得混入别的主题：证明内嵌的确实只有一套样式链。"""
    html = assemble_document(envelope(), title="标题", template_name="Office")["html"]

    assert THEME_MARKERS["Office"] in viewer_assets.theme_css_chain("Office")
    assert THEME_MARKERS["Office"] in html
    for other in ("Modern", "Vscode"):
        assert THEME_MARKERS[other] not in html, other


def test_the_delivered_document_uses_classic_scripts_only():
    """交付物是 file:// 单文件：运行期不得出现 ES module（CORS 会拦）。"""
    html = assemble_document(envelope(), title="标题", template_name="modern")["html"]

    assert 'type="module"' not in html
    assert "<script>" in html


def test_the_consumers_no_longer_read_the_asset_knowledge_from_config():
    """源码级锁：资产知识只有一处来源（与 C3 的 runtime 锁同构）。"""
    for consumer in CONSUMERS:
        leaked = imported_from(consumer, "core.config") & MOVED_FROM_CONFIG

        assert leaked == set(), (consumer, leaked)


def test_the_gui_registry_comes_from_the_asset_layer():
    assert imported_from("gui/api.py", "core.viewer_assets") == {"normalize_theme_id", "theme_ids"}
    assert "TEMPLATES_DIR" not in (ROOT / "gui" / "api.py").read_text(encoding="utf-8")
