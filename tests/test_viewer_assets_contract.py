"""Phase 6A: the reader asset layer is the single owner of Viewer/theme knowledge.

`core/viewer_assets.py` answers "what is a reader document made of, and where do
those files live". Before 6A that knowledge was spread over `core/config.py`, both
assembly paths and the GUI dropdown, so moving one file touched five modules.

The contracts below describe **today's** documents. Phase 6C replaced the
"exactly one theme is injected" contract with "every builtin theme is injected
exactly once"; that payload contract now lives in
`tests/test_theme_bundle_contract.py`.
"""

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import html_assembly, viewer_assets  # noqa: E402
from core.config import (  # noqa: E402
    PLACEHOLDER_CONTENT,
    PLACEHOLDER_THEME_ID,
    PLACEHOLDER_THEME_MENU,
    PLACEHOLDER_TITLE,
    PLACEHOLDER_TOC,
)
from core.html_assembly import assemble_document  # noqa: E402

# Phase 6B unified these three: the selector, the metadata id and the directory
# name are the same lowercase id under `themes/builtin/`.
SELECTABLE = ["modern", "office", "vscode"]
BASE = "base"
OLD_ASSET_PATHS = (
    "templates/viewer.js",
    "templates/print.css",
    "templates/default",
    "templates/Modern",
    "templates/Office",
    "templates/Vscode",
    # 预防性：新的 canonical id 也不得回到 templates/（Phase 6D 收口）。
    "templates/base",
    "templates/modern",
    "templates/office",
    "templates/vscode",
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


def write_theme(root, theme_id, files=None, **metadata):
    """Create a theme directory with a metadata.json and its declared CSS files."""
    directory = root / theme_id
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"id": theme_id, "name": theme_id.title()}
    payload.update(metadata)
    if files:
        payload["files"] = [name for name, _ in files]
    (directory / "metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    for name, css in files or []:
        (directory / name).write_text(css, encoding="utf-8")
    return directory


def test_the_selectable_builtin_registry_is_exactly_the_three_builtins():
    """Phase 7B：`theme_ids()` 变成「已安装的可选主题」；没装外置主题时等价于 builtin。"""
    assert viewer_assets.builtin_theme_ids() == SELECTABLE
    assert viewer_assets.external_theme_ids() == []
    assert viewer_assets.theme_ids() == SELECTABLE


def test_a_theme_can_come_from_the_user_assets_directory(tmp_path, monkeypatch):
    """Phase 7B：同一个 loader 读两个来源；外置主题自带它声明的视觉 CSS。"""
    external = tmp_path / "external"
    write_theme(
        external,
        "paper",
        files=[
            ("variables.css", ":root{--paper:1}\n"),
            ("content.css", "html[data-theme-id=paper]{--paper:2}\n"),
        ],
    )
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))

    assert viewer_assets.external_theme_ids() == ["paper"]
    assert viewer_assets.theme_source("paper") == viewer_assets.SOURCE_EXTERNAL
    assert viewer_assets.theme_source("modern") == viewer_assets.SOURCE_BUILTIN
    assert viewer_assets.theme_ids() == ["modern", "office", "paper", "vscode"]
    assert viewer_assets.builtin_theme_ids() == SELECTABLE
    assert viewer_assets.theme_metadata("paper")["name"] == "Paper"
    assert viewer_assets.theme_files("paper") == ["variables.css", "content.css"]
    assert viewer_assets.theme_css_text("paper").count("--paper") == 2


def test_a_user_theme_may_not_shadow_a_builtin_id(tmp_path, monkeypatch):
    """builtin 优先：同 id 的用户目录必须被忽略，而不是悄悄替换随包主题。"""
    external = tmp_path / "external"
    write_theme(external, "modern", files=[("theme.css", ":root{--fake:1}\n")])
    write_theme(external, "base", files=[("theme.css", ":root{--fake:2}\n")])
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))

    assert viewer_assets.external_theme_ids() == []
    assert viewer_assets.theme_source("modern") == viewer_assets.SOURCE_BUILTIN
    assert "--fake" not in viewer_assets.theme_css_text("modern")


@pytest.mark.parametrize("payload", ('"broken"', "[1]", "{}"))
def test_unusable_metadata_is_not_an_installed_theme(
    tmp_path, monkeypatch, payload
):
    """F1：根不是 object（或为空 object）的 metadata.json 不得击穿 registry。

    `_metadata_at()` 声明返回 `dict`，而 `_scan_theme_ids()` 直接对它 `.get()`，所以
    `"broken"` / `[1]` 这样的文件必须与「缺失 / 解析失败」同类：目录不算主题，
    configured 里出现它归 `missing`，状态查询与转换选择都不能抛 AttributeError。
    `"broken"` / `[1]` 是这次的红用例，`"{}"`（object 但为空）是边界锁 —— 它修复前
    也走 `if not metadata` 分支、本来就绿，用来钉住契约里「object 为空」这一句。
    """
    external = tmp_path / "external"
    broken = external / "broken"
    broken.mkdir(parents=True)
    (broken / "metadata.json").write_text(payload, encoding="utf-8")
    write_theme(
        external, "paper", files=[("theme.css", 'html[data-theme-id="paper"]{--p:1}\n')]
    )
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))

    from core import external_themes

    assert viewer_assets.external_theme_ids() == ["paper"]
    assert viewer_assets.theme_ids() == ["modern", "office", "paper", "vscode"]
    assert viewer_assets.theme_metadata("broken") == {}

    with pytest.raises(ValueError):
        viewer_assets.validate_theme("broken")

    selection = external_themes.resolve_theme_selection(["broken", "paper"])

    assert selection["external_ids"] == ["paper"]
    assert any("broken" in warning for warning in selection["warnings"])


def test_selectable_themes_are_builtins_plus_the_selected_external_ones(tmp_path, monkeypatch):
    """文档携带哪些主题：builtin 永远全带 + 本次选中的已安装外置主题。"""
    external = tmp_path / "external"
    write_theme(
        external, "paper", files=[("theme.css", 'html[data-theme-id="paper"]{--paper:1}\n')]
    )
    write_theme(
        external,
        "academic",
        files=[("theme.css", 'html[data-theme-id="academic"]{--academic:1}\n')],
    )
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))

    from core import external_themes

    def menu_of(requested):
        return external_themes.resolve_theme_selection(requested)["menu_ids"]

    assert menu_of(["paper"]) == ["modern", "office", "paper", "vscode"]
    assert menu_of(["paper", "academic"]) == [
        "academic",
        "modern",
        "office",
        "paper",
        "vscode",
    ]
    assert menu_of(["ghost"]) == SELECTABLE
    assert menu_of([]) == SELECTABLE


def test_every_builtin_declares_the_css_files_it_contributes():
    """AGENTS section 14：metadata 声明实际 CSS 文件列表；builtin 用同一字段。"""
    for theme_id in viewer_assets.theme_ids(include_hidden=True):
        declared = viewer_assets.theme_metadata(theme_id)["files"]
        assert viewer_assets.theme_files(theme_id), theme_id
        assert viewer_assets.theme_files(theme_id) == declared


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
    # Phase 6D：把最终 ownership 锁成白名单 —— templates/ 只属于批量索引页这一个独立表面。
    assert sorted(entry.name for entry in (ROOT / "templates").iterdir()) == ["index"]


# The theme payload contracts live in `tests/test_theme_bundle_contract.py` now.
# Before Phase 6C this module asserted "exactly one theme is injected"; 6C replaced
# that target with "every builtin theme is injected exactly once, and the document's
# own default is active in the markup", which is a deliberate transition and not a
# retired assertion.


def test_the_delivered_document_uses_classic_scripts_only():
    """交付物是 file:// 单文件：运行期不得出现 ES module（CORS 会拦）。"""
    html = assemble_document(envelope(), title="标题", template_name="modern")["html"]

    assert 'type="module"' not in html
    assert "<script>" in html


@pytest.mark.parametrize(
    "placeholder",
    (
        PLACEHOLDER_TITLE,
        PLACEHOLDER_CONTENT,
        PLACEHOLDER_TOC,
        PLACEHOLDER_THEME_ID,
        PLACEHOLDER_THEME_MENU,
    ),
)
def test_an_incomplete_shell_is_refused_before_assembly(placeholder, monkeypatch):
    """shell 缺任一必需占位符时装配必须失败，而不是产出"看起来对"的文档。

    5 个占位符都是必需的：前三个是文档内容，6C 新增的两个是**默认主题**与**主题菜单**。
    少了它们的产物不会报错，只会在浏览器里表现为"主题不对/菜单没有"，因此拒绝必须发生在
    装配期（与"缺 builtin theme 即硬失败"同一原则）。
    """
    assert placeholder in viewer_assets.viewer_shell_text(), placeholder
    incomplete = viewer_assets.viewer_shell_text().replace(placeholder, "")
    monkeypatch.setattr(html_assembly, "viewer_shell_text", lambda: incomplete)

    with pytest.raises(ValueError, match="缺少占位符"):
        assemble_document(envelope(), title="标题", template_name="modern")


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
    # Phase 7B: theme_ids() also reports installed user themes, so the existing
    # dropdown asks for the builtin set explicitly until Phase 9 adds their surface.
    # Phase 8C keeps the theme state aggregation in core/external_themes.py, so the
    # bridge does not read the registry itself -- only the two names it always did.
    assert imported_from("gui/api.py", "core.viewer_assets") == {
        "builtin_theme_ids",
        "normalize_theme_id",
    }
    assert "TEMPLATES_DIR" not in (ROOT / "gui" / "api.py").read_text(encoding="utf-8")
