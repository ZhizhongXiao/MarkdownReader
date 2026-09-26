"""Phase 6C: every document carries the whole builtin theme bundle.

The reader ships base + modern + office + vscode in each HTML and switches between
them at runtime, so three things must hold at assembly time:

* each builtin theme is injected exactly once (a duplicated bundle would mean
  duplicated payload, and a missing one a theme that cannot be selected);
* the document's own default theme is already active in the markup, before any
  script runs -- the reader must not flash an unstyled page while JS boots;
* the page carries what the switcher needs (the menu with readable names) without
  reaching for anything external, and still ships exactly one classic script.

`tests/js/viewer.test.js` covers the runtime half (THEME1-THEME8); this module
covers the delivered artifact.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from theme_tree import broken_theme_tree  # noqa: E402

from core import viewer_assets  # noqa: E402
from core.html_assembly import assemble_document  # noqa: E402

SELECTABLE = ("modern", "office", "vscode")
# The first-line banner of each theme file: it appears in exactly one source file,
# so counting it in the document proves that file was injected once.
THEME_MARKERS = {
    "base": "/* MarkdownReader Base Theme */",
    "modern": "/* MarkdownReader Modern Theme */",
    "office": "/* MarkdownReader Office Template */",
    "vscode": "/* MarkdownReader VS Code Template */",
}
LABELS = {"modern": "Modern", "office": "Office", "vscode": "VS Code"}


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


def assembled(template: str) -> dict:
    return assemble_document(envelope(), title="标题", template_name=template)


def test_every_builtin_theme_is_injected_exactly_once():
    for template in SELECTABLE:
        html = assembled(template)["html"]

        for theme_id, marker in THEME_MARKERS.items():
            assert html.count(marker) == 1, (template, theme_id, html.count(marker))


def test_the_injection_ledger_names_each_theme_separately():
    """账本按主题分开记录：重复内嵌或漏掉一套都能被指出是哪一套。"""
    labels = [entry["label"] for entry in assembled("office")["injections"]]

    for theme_id in THEME_MARKERS:
        assert labels.count("theme:" + theme_id) == 1, (theme_id, labels)
    assert labels.count("viewer-js") == 1
    assert labels.count("viewer-css") == 1
    assert labels.count("print") == 1


@pytest.mark.parametrize("template", SELECTABLE)
def test_the_document_default_theme_is_active_in_the_markup(template):
    """初始主题必须在 HTML 里就成立，而不是等 JS 补写（否则本地打开会闪一下）。"""
    html = assembled(template)["html"]

    assert f'<html lang="zh-CN" data-theme-id="{template}">' in html
    assert f'<body class="theme-{template}">' in html
    for other in SELECTABLE:
        if other != template:
            assert f'<body class="theme-{other}">' not in html


def test_the_switcher_menu_ships_with_readable_names():
    html = assembled("modern")["html"]

    assert 'id="btn-theme"' in html
    assert 'id="theme-menu"' in html
    for theme_id, label in LABELS.items():
        assert f'data-theme-id="{theme_id}"' in html, theme_id
        assert f">{label}</button>" in html, (theme_id, label)


def test_the_document_stays_standalone_and_runs_one_classic_script():
    html = assembled("modern")["html"]

    assert 'type="module"' not in html
    assert "<script src=" not in html
    assert "<link" not in html
    assert "http://" not in html and "https://" not in html


def make_user_theme(root, theme_id, css, **metadata):
    """Write an installed user theme under ``root``."""
    directory = root / theme_id
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"id": theme_id, "name": theme_id.title(), "files": list(css)}
    payload.update(metadata)
    (directory / "metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    for name, text in css.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


def test_a_selected_user_theme_is_bundled_with_its_assets_inlined(tmp_path, monkeypatch):
    """7E：文档携带 builtin + 本次选中的外置主题，且外置主题的资源必须内嵌。"""
    external = tmp_path / "external"
    source = make_user_theme(
        external, "paper", {"theme.css": 'html[data-theme-id="paper"]{--paper:1}'}
    )
    (source / "assets").mkdir()
    (source / "assets" / "bg.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (source / "theme.css").write_text(
        'html[data-theme-id="paper"]{background:url(assets/bg.png)}', encoding="utf-8"
    )
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))

    built = assemble_document(
        envelope(), title="标题", template_name="modern", external_themes=["paper"]
    )
    labels = [entry["label"] for entry in built["injections"]]

    assert labels.count("theme:paper") == 1
    assert labels.count("theme:office") == 1, "builtin 仍然全带"
    assert "data:image/png;base64," in built["html"], "外置主题的资源必须内嵌"
    assert (
        '<button type="button" class="theme-option" data-theme-id="paper">Paper</button>'
        in built["html"]
    ), "菜单必须包含已选中的外置主题，且用 metadata 的可读名称"


def test_an_installed_but_unselected_user_theme_stays_out(tmp_path, monkeypatch):
    external = tmp_path / "external"
    make_user_theme(external, "paper", {"theme.css": 'html[data-theme-id="paper"]{--paper:1}'})
    make_user_theme(
        external, "academic", {"theme.css": 'html[data-theme-id="academic"]{--academic:1}'}
    )
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))

    built = assemble_document(
        envelope(), title="标题", template_name="modern", external_themes=["paper"]
    )
    labels = [entry["label"] for entry in built["injections"]]

    assert labels.count("theme:paper") == 1
    assert "theme:academic" not in labels
    assert "--academic" not in built["html"]


def test_a_configured_theme_that_is_not_installed_is_ignored(tmp_path, monkeypatch):
    """AGENTS section 17：配置里存在但已删除的主题忽略即可，转换继续。"""
    external = tmp_path / "external"
    external.mkdir()
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))

    built = assemble_document(
        envelope(), title="标题", template_name="modern", external_themes=["ghost"]
    )
    labels = [entry["label"] for entry in built["injections"]]

    assert labels.count("theme:ghost") == 0
    assert labels.count("theme:modern") == 1
    assert '<html lang="zh-CN" data-theme-id="modern">' in built["html"]


def test_a_document_default_user_theme_is_bundled_even_when_unselected(tmp_path, monkeypatch):
    """决策 3：template 指向已安装但未选中的外置主题时，自动补入本文档。"""
    external = tmp_path / "external"
    make_user_theme(external, "paper", {"theme.css": 'html[data-theme-id="paper"]{--paper:1}'})
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))

    built = assemble_document(
        envelope(), title="标题", template_name="paper", external_themes=[]
    )
    labels = [entry["label"] for entry in built["injections"]]

    assert labels.count("theme:paper") == 1
    assert '<html lang="zh-CN" data-theme-id="paper">' in built["html"]
    assert '<body class="theme-paper">' in built["html"]


def test_a_missing_required_theme_fails_instead_of_shipping_partial_css(tmp_path, monkeypatch):
    """builtin 主题是随包必需资产：缺一套必须硬失败，不得产出缺主题变量的 HTML。

    6B 及以前这一步只降级（记一条 warning，文档照常生成，只是没有主题变量）。本用例
    正是那次**有意语义变化**的锁：要求"缺文件 → 抛错并指明缺哪一套"，而不是"缺文件
    → 少一套主题的成品"。builtin 主题既是 spec 的必需文件，半成品不应有出口。
    """
    monkeypatch.setattr(viewer_assets, "_THEMES_ROOT", str(broken_theme_tree(tmp_path)))

    with pytest.raises(ValueError) as failure:
        viewer_assets.builtin_theme_css_text()
    assert "office" in str(failure.value), "错误必须指出缺的是哪一套主题"

    with pytest.raises(ValueError, match="主题资源不可用"):
        assembled("modern")
