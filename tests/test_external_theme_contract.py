"""Phase 7C/7D: external themes are CSS-only user content.

An external theme is a directory of CSS that must not be able to (a) reach the
network, (b) escape its own directory, (c) inject markup through the `<style>`
element it will be embedded in, or (d) take a builtin id. These cases pin the
validator, the import/remove/export operations, and the asset inlining that keeps a
generated document working after the theme has been deleted from MarkdownReader.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import external_themes, viewer_assets  # noqa: E402

TEMPLATE = ROOT / "themes" / "template"
VALID_CSS = 'html[data-theme-id="my-theme"] body.theme-my-theme{--x:1}\n'


def theme_files(root: Path, dirname: str, css: dict, **metadata) -> Path:
    """Write a theme directory: metadata.json plus the CSS files it declares."""
    directory = root / dirname
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"id": dirname, "name": dirname.title(), "files": list(css)}
    payload.update(metadata)
    (directory / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    for name, text in css.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


@pytest.fixture()
def install_root(tmp_path, monkeypatch):
    """Point the installed user themes at a temporary directory."""
    root = tmp_path / "external"
    root.mkdir()
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(root))
    return root


def test_the_packaged_template_is_a_valid_theme():
    """AGENTS section 16：themes/template/ 是官方开发模板，导出后即可用。"""
    for name in (
        "metadata.json",
        "variables.css",
        "content.css",
        "components.css",
        "print.css",
        "README.md",
    ):
        assert (TEMPLATE / name).is_file(), name
    assert (TEMPLATE / "assets").is_dir()

    metadata = external_themes.validate_theme_directory(str(TEMPLATE))
    assert metadata["id"] == "my-theme"
    assert metadata["files"] == ["variables.css", "content.css", "components.css", "print.css"]


def test_a_valid_theme_can_be_imported_and_removed(tmp_path, install_root):
    source = theme_files(tmp_path, "my-theme", {"theme.css": VALID_CSS}, name="Paper")

    assert external_themes.import_theme(str(source)) == "my-theme"
    assert (install_root / "my-theme" / "metadata.json").is_file()
    assert viewer_assets.external_theme_ids() == ["my-theme"]

    external_themes.remove_theme("my-theme")
    assert viewer_assets.external_theme_ids() == []


def test_importing_the_same_id_twice_needs_replace(tmp_path, install_root):
    source = theme_files(tmp_path, "my-theme", {"theme.css": VALID_CSS})
    external_themes.import_theme(str(source))

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(source))
    assert external_themes.import_theme(str(source), replace=True) == "my-theme"


@pytest.mark.parametrize(
    "css, reason",
    (
        ('@import url("https://example.com/x.css");\n', "@import"),
        ("body{background:url(https://example.com/x.png)}\n", "远程"),
        ("body{background:url(//cdn.example.com/x.png)}\n", "远程"),
        ("body{background:url(assets/x.png)}\n", "不存在"),
        ("body{color:expression(alert(1))}\n", "expression"),
        ("body{behavior:url(#default#userData)}\n", "behavior"),
        ("body{background:url(javascript:alert(1))}\n", "javascript"),
        ("</style><script>alert(1)</script>\n", "</style"),
    ),
)
def test_css_that_could_inject_or_reach_the_network_is_refused(
    tmp_path, install_root, css, reason
):
    source = theme_files(tmp_path, "bad-theme", {"theme.css": css})

    with pytest.raises(external_themes.ExternalThemeError) as failure:
        external_themes.import_theme(str(source))
    assert reason in str(failure.value), str(failure.value)


def test_a_declared_file_may_not_escape_the_theme_directory(tmp_path, install_root):
    (tmp_path / "outside.css").write_text("html{--outside:1}\n", encoding="utf-8")
    source = theme_files(tmp_path, "escape", {"theme.css": VALID_CSS})
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    metadata["files"] = ["../outside.css"]
    (source / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(external_themes.ExternalThemeError) as failure:
        external_themes.import_theme(str(source))
    assert ".." in str(failure.value) or "逃逸" in str(failure.value)


@pytest.mark.parametrize("bad_id", ("modern", "base", "default", "Bad", "9theme", "t", "x" * 40))
def test_a_reserved_or_malformed_id_is_refused(tmp_path, install_root, bad_id):
    source = theme_files(tmp_path, "source", {"theme.css": VALID_CSS}, id=bad_id)

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(source))


def test_missing_files_or_metadata_are_refused(tmp_path, install_root):
    source = theme_files(tmp_path, "gap", {"theme.css": VALID_CSS})
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    metadata["files"] = ["theme.css", "missing.css"]
    (source / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(source))

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(empty))


def test_a_declared_file_must_be_css(tmp_path, install_root):
    source = tmp_path / "script-theme"
    source.mkdir()
    (source / "metadata.json").write_text(
        json.dumps({"id": "script-theme", "name": "S", "files": ["theme.js"]}),
        encoding="utf-8",
    )
    (source / "theme.js").write_text("alert(1)\n", encoding="utf-8")

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(source))


def test_assets_are_inlined_so_a_deleted_theme_still_renders(tmp_path, install_root):
    """Phase 7 验收 3：本地资源必须内嵌，删掉主题后已生成的 HTML 仍然可用。"""
    source = theme_files(tmp_path, "my-theme", {"theme.css": VALID_CSS})
    assets = source / "assets"
    assets.mkdir()
    (assets / "bg.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (source / "theme.css").write_text(
        'html[data-theme-id="my-theme"]{background:url(assets/bg.png)}\n', encoding="utf-8"
    )
    external_themes.import_theme(str(source))

    css = external_themes.inline_theme_css("my-theme")
    assert "data:image/png;base64," in css
    assert "url(assets/bg.png)" not in css

    external_themes.remove_theme("my-theme")
    assert css.count("data:image/png;base64,") == 1


def test_export_then_import_round_trips(tmp_path, install_root):
    """Phase 7 验收 1+2：可以导出主题模板；用户改完之后可以重新导入。"""
    written = external_themes.export_template(str(tmp_path / "exported"))

    assert Path(written).is_dir()
    assert (Path(written) / "metadata.json").is_file()
    assert external_themes.import_theme(written) == "my-theme"
    assert viewer_assets.external_theme_ids() == ["my-theme"]


def test_the_checker_and_the_loader_agree_on_external_references():
    """一个策略、两处实现：工具链与装配期必须认同「什么算外部引用」。"""
    from tools import standalone_closure

    assert external_themes.CSS_URL_PATTERN.pattern == standalone_closure.CSS_URL_PATTERN.pattern
    assert (
        external_themes.CSS_IMPORT_PATTERN.pattern
        == standalone_closure.CSS_IMPORT_PATTERN.pattern
    )
    assert external_themes.INLINE_PREFIXES == standalone_closure.INLINE_PREFIXES
