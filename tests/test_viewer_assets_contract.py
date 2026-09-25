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

# Phase 6B unified these three: the selector, the metadata id and the directory
# name are the same lowercase id under `themes/builtin/`.
SELECTABLE = ["modern", "office", "vscode"]
BASE = "base"
THEME_MARKERS = {
    "modern": "--modern-guide-border",
    "office": "--office-page-bg",
    "vscode": "--vscode-preview-font",
}
OLD_ASSET_PATHS = (
    "templates/viewer.js",
    "templates/print.css",
    "templates/default",
    "templates/Modern",
    "templates/Office",
    "templates/Vscode",
)

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
    assert viewer_assets.theme_metadata(BASE)["hidden"] is True
    assert BASE not in viewer_assets.theme_ids()
    assert BASE in viewer_assets.theme_ids(include_hidden=True)


def test_every_builtin_lives_under_its_own_id():
    """Phase 6B：注册表项 == metadata.id == 目录名，三重身份合一。"""
    for theme_id in viewer_assets.theme_ids(include_hidden=True):
        assert viewer_assets.theme_metadata(theme_id)["id"] == theme_id, theme_id
        assert (ROOT / "themes" / "builtin" / theme_id).is_dir(), theme_id


def test_the_old_asset_paths_are_gone():
    """搬迁后旧路径不得残留：阅读器资产只在 viewer/ 与 themes/builtin/ 下。"""
    left = [relative for relative in OLD_ASSET_PATHS if (ROOT / relative).exists()]

    assert left == [], left
    assert (ROOT / "templates" / "index" / "index.js").is_file(), "索引页保持在原处"


@pytest.mark.parametrize("theme", SELECTABLE)
def test_a_current_document_injects_the_selected_theme_exactly_once(theme):
    """今天每份文档只内嵌所选主题，各通道恰好一次（6C 才内嵌全部 builtin）。"""
    assembled = assemble_document(envelope(), title="标题", template_name=theme)
    labels = [entry["label"] for entry in assembled["injections"]]

    assert labels.count("viewer-css") == 1
    assert labels.count("theme") == 1
    assert labels.count("print") == 1
    assert labels.count("viewer-js") == 1
    assert f'<body class="theme-{theme}">' in assembled["html"]


def test_an_unselected_theme_does_not_reach_the_document():
    """选 office 时不得混入别的主题：证明内嵌的确实只有一套样式链。"""
    html = assemble_document(envelope(), title="标题", template_name="office")["html"]

    assert THEME_MARKERS["office"] in viewer_assets.theme_css_chain("office")
    assert THEME_MARKERS["office"] in html
    for other in ("modern", "vscode"):
        assert THEME_MARKERS[other] not in html, other


def test_the_delivered_document_uses_classic_scripts_only():
    """交付物是 file:// 单文件：运行期不得出现 ES module（CORS 会拦）。"""
    html = assemble_document(envelope(), title="标题", template_name="modern")["html"]

    assert 'type="module"' not in html
    assert "<script>" in html


def test_the_viewer_payload_is_assembled_from_the_manifest_in_order():
    """Phase 6B：模块是同一个 IIFE 的片段，按 manifest 顺序、空分隔拼回一个脚本。

    逐字节相等的最终证据是 samples/demo.html（test_demo_generation 直接比对入库标本），
    这里锁的是拼接规则本身：模块齐全、顺序唯一、都以换行结尾、结果只有一个 IIFE。
    """
    modules = viewer_assets.viewer_js_modules()
    chunks = [(ROOT / "viewer" / "js" / name).read_text(encoding="utf-8") for name in modules]
    payload = viewer_assets.shared_viewer_js_text()

    assert modules == list(dict.fromkeys(modules)), "manifest 不得重复模块"
    assert all(chunk.strip() for chunk in chunks), "模块不得为空"
    assert all(chunk.endswith("\n") for chunk in chunks), "模块必须以换行结尾"
    assert payload == "\ufeff" + "".join(chunks)
    # 外壳仍是同一个 IIFE：BOM 在前、"use strict" 只有一处、结尾闭合 —— 拼接不会
    # 意外产生第二份包装或半截函数。
    assert payload.startswith("\ufeff")
    assert payload.count('"use strict";') == 1
    # 包装先于指令：拼接不会意外产生第二处包装或半截函数。
    assert payload.index("(function () {") < payload.index('"use strict";')
    assert payload.rstrip("\n").endswith("})();")


def test_the_consumers_no_longer_read_the_asset_knowledge_from_config():
    """源码级锁：资产知识只有一处来源（与 C3 的 runtime 锁同构）。"""
    for consumer in CONSUMERS:
        leaked = imported_from(consumer, "core.config") & MOVED_FROM_CONFIG

        assert leaked == set(), (consumer, leaked)


def test_the_config_module_no_longer_owns_asset_paths():
    assert "TEMPLATES_DIR" not in (ROOT / "core" / "config.py").read_text(encoding="utf-8")


def test_the_gui_registry_comes_from_the_asset_layer():
    assert imported_from("gui/api.py", "core.viewer_assets") == {"normalize_theme_id", "theme_ids"}
    assert "TEMPLATES_DIR" not in (ROOT / "gui" / "api.py").read_text(encoding="utf-8")
