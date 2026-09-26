"""Phase 7C/7D: external themes are CSS-only user content.

An external theme is a directory of CSS that must not be able to (a) reach the
network, (b) escape its own directory, (c) inject markup through the `<style>`
element it will be embedded in, or (d) take a builtin id. These cases pin the
validator, the import/remove/export operations, and the asset inlining that keeps a
generated document working after the theme has been deleted from MarkdownReader.
"""

import json
import os
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


def scoped(theme_id: str, body: str = "--x:1") -> str:
    """Return the canonical scoped spelling every theme rule must use."""
    return 'html[data-theme-id="' + theme_id + '"]{' + body + '}\n'


def test_a_theme_tampered_after_installation_is_refused(tmp_path, install_root):
    """审计阻断项 1：import 只在导入时校验，消费时必须再校验一次。"""
    source = theme_files(tmp_path, "my-theme", {"theme.css": scoped("my-theme")})
    external_themes.import_theme(str(source))
    (install_root / "my-theme" / "theme.css").write_text(
        "</style><script>alert(1)</script>\n", encoding="utf-8"
    )

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.inline_theme_css("my-theme")
    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.resolve_theme_selection(["my-theme"])


def test_a_theme_hand_copied_into_the_root_is_refused(install_root):
    """审计阻断项 1：绕过 import 直接放进安装目录的目录同样要过 gate。"""
    directory = install_root / "manual"
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        json.dumps({"id": "manual", "name": "Manual", "files": ["theme.css"]}),
        encoding="utf-8",
    )
    (directory / "theme.css").write_text("body{color:red}\n", encoding="utf-8")

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.inline_theme_css("manual")


def test_an_installed_directory_must_match_its_metadata_id(install_root):
    directory = install_root / "renamed"
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        json.dumps({"id": "other", "name": "Other", "files": ["theme.css"]}),
        encoding="utf-8",
    )
    (directory / "theme.css").write_text(scoped("other"), encoding="utf-8")

    with pytest.raises(external_themes.ExternalThemeError) as failure:
        external_themes.inline_theme_css("renamed")
    assert "目录名" in str(failure.value)


@pytest.mark.parametrize(
    "declaration, reason",
    (
        ('background:url("https://example.invalid/a(b).png")', "远程"),
        ('background:url("//cdn.example.invalid/x.png")', "远程"),
        ('background:url("data:text/html;base64,AAAA")', "data URI"),
        ('background:url("data:image/svg+xml;base64,AAAA")', "data URI"),
        ("background:url(assets/missing.png)", "不存在"),
    ),
)


def test_references_that_leave_the_document_are_refused(
    tmp_path, install_root, declaration, reason
):
    """审计项 3/11/12/13：远程、scheme 混淆、非白名单 data URI、缺失资源全部拒绝。"""
    source = theme_files(tmp_path, "my-theme", {"theme.css": scoped("my-theme", declaration)})

    with pytest.raises(external_themes.ExternalThemeError) as failure:
        external_themes.import_theme(str(source))
    assert reason in str(failure.value), str(failure.value)


def test_a_css_escape_cannot_hide_a_scheme(tmp_path, install_root):
    """审计附加项 11：`url("https\\3a //…")` 这类 scheme 混淆必须 fail closed。

    用 chr(92) 构造反斜杠，避免测试文件本身被转义层级搞混。
    """
    escaped = "https" + chr(92) + "3a //example.invalid/x.png"
    source = theme_files(
        tmp_path,
        "my-theme",
        {"theme.css": scoped("my-theme", 'background:url("' + escaped + '")')},
    )

    with pytest.raises(external_themes.ExternalThemeError) as failure:
        external_themes.import_theme(str(source))
    assert "转义" in str(failure.value), str(failure.value)


def test_an_allow_listed_data_uri_is_accepted(tmp_path, install_root):
    source = theme_files(
        tmp_path,
        "my-theme",
        {"theme.css": scoped("my-theme", 'background:url("data:image/png;base64,AAAA")')},
    )

    assert external_themes.import_theme(str(source)) == "my-theme"


@pytest.mark.parametrize(
    "css",
    (
        'html[data-theme-id="my-theme"]{background:url(x.png)}/* unclosed',
        'html[data-theme-id="my-theme"]{content:"unclosed',
        'html[data-theme-id="my-theme"]{color:red}\\',
    ),
)
def test_structurally_unprovable_css_fails_closed(tmp_path, install_root, css):
    """审计项：未闭合注释/字符串、孤立转义 —— 解析不了就拒绝，不猜。"""
    source = theme_files(tmp_path, "my-theme", {"theme.css": css})

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(source))


@pytest.mark.parametrize("parent", ("modern", "office", "vscode"))
def test_an_external_theme_may_not_extend_a_selectable_builtin(tmp_path, install_root, parent):
    """审计阻断项 4：selectable builtin 的规则按自身 id scoped，继承它们是语义假的。"""
    source = theme_files(
        tmp_path, "my-theme", {"theme.css": scoped("my-theme")}, extends=parent
    )

    with pytest.raises(external_themes.ExternalThemeError) as failure:
        external_themes.import_theme(str(source))
    assert "extends" in str(failure.value)


def test_an_external_theme_may_extend_base_or_nothing(tmp_path, install_root):
    for parent in ("base", None):
        directory = tmp_path / ("with-" + str(parent))
        source = theme_files(
            directory, "my-theme", {"theme.css": scoped("my-theme")}, extends=parent
        )
        assert external_themes.import_theme(str(source), replace=True) == "my-theme"


def test_an_external_theme_may_not_extend_another_external(tmp_path, install_root):
    parent = theme_files(tmp_path, "parent", {"theme.css": scoped("parent")})
    assert external_themes.import_theme(str(parent)) == "parent"
    child = theme_files(
        tmp_path / "child-src", "child", {"theme.css": scoped("child")}, extends="parent"
    )

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(child))


@pytest.mark.parametrize(
    "css",
    (
        "body{color:red}\n",
        ":root{--x:1}\n",
        'html{--x:1}\n',
        'html[data-theme-id="my-theme"] body.theme-my-theme{--x:1}\n',
    ),
)
def test_unscoped_rules_are_refused(tmp_path, install_root, css):
    """审计项：未 scoped 的规则会污染其他主题，必须拒绝（最后一条是 scoped，正例）。"""
    source = theme_files(tmp_path, "my-theme", {"theme.css": css})

    if css.startswith('html[data-theme-id="my-theme"]'):
        assert external_themes.import_theme(str(source)) == "my-theme"
    else:
        with pytest.raises(external_themes.ExternalThemeError) as failure:
            external_themes.import_theme(str(source))
        assert "scoped" in str(failure.value)


def test_media_queries_recurse_and_still_require_scope(tmp_path, install_root):
    good = theme_files(
        tmp_path / "good",
        "my-theme",
        {"theme.css": "@media print {\n" + scoped("my-theme") + "}\n"},
    )
    assert external_themes.import_theme(str(good)) == "my-theme"

    bad = theme_files(
        tmp_path / "bad", "other", {"theme.css": "@media print {\nbody{color:red}\n}\n"}
    )
    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(bad))


@pytest.mark.parametrize(
    "css",
    (
        "@keyframes pulse { from { opacity:0 } }\n" + scoped("my-theme"),
        "@font-face { font-family: X; src: url(a.woff2) }\n" + scoped("my-theme"),
        "@page { margin: 1cm }\n" + scoped("my-theme"),
        '@charset "utf-8";\n' + scoped("my-theme"),
        "@layer base;\n" + scoped("my-theme"),
        "@namespace svg url(http://www.w3.org/2000/svg);\n" + scoped("my-theme"),
    ),
)
def test_at_rules_with_global_names_are_refused(tmp_path, install_root, css):
    """@keyframes/@font-face 拥有全局命名；@page 无法 scope；@charset/@layer/@namespace 无意义。"""
    source = theme_files(tmp_path, "my-theme", {"theme.css": css})

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(source))


def test_the_payload_budget_counts_inlined_assets(tmp_path, install_root, monkeypatch):
    """审计次要项：预算按最终内嵌载荷（含 base64 膨胀）计算，而不是目录大小。"""
    source = theme_files(
        tmp_path, "my-theme", {"theme.css": scoped("my-theme", "background:url(assets/big.png)")}
    )
    (source / "assets").mkdir()
    (source / "assets" / "big.png").write_bytes(b"\x89PNG" + b"A" * 512)
    monkeypatch.setattr(external_themes, "MAX_ASSET_BYTES", 64)

    with pytest.raises(external_themes.ExternalThemeError) as failure:
        external_themes.import_theme(str(source))
    assert "上限" in str(failure.value)


def test_an_asset_reached_through_a_symlink_is_refused(tmp_path, install_root):
    """审计附加项 12：真实路径逃逸（symlink/junction）必须拒绝。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.png").write_bytes(b"\x89PNG")
    source = theme_files(
        tmp_path, "my-theme", {"theme.css": scoped("my-theme", "background:url(link/secret.png)")}
    )
    try:
        os.symlink(str(outside), str(source / "link"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境无法创建 symlink")

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.import_theme(str(source))


@pytest.mark.parametrize(
    "declaration",
    (
        'background-image:image-set("https://example.invalid/x.png" 1x)',
        'background:-webkit-image-set("https://example.invalid/x.png" 1x)',
        'background:src("https://example.invalid/x.png")',
        'background:image("https://example.invalid/x.png")',
        'background:cross-fade(url(a.png), url(b.png), 50%)',
        'background:element(#probe)',
    ),
)
def test_unscanned_resource_functions_fail_closed(tmp_path, install_root, declaration):
    """审计 follow-up #2：image-set()/src() 等能命名远程资源的函数一律拒绝。

    `image-set()` 接受裸 <string> 作为图片 URL，`src()` 是 <url> 的另一种拼写，因此
    "只认 url() 与 @import" 的扫描器会被合法 CSS 绕过。
    """
    source = theme_files(tmp_path, "my-theme", {"theme.css": scoped("my-theme", declaration)})

    with pytest.raises(external_themes.ExternalThemeError) as failure:
        external_themes.import_theme(str(source))
    assert "未审计" in str(failure.value), str(failure.value)


def test_a_gradient_stays_legal(tmp_path, install_root):
    """正例对照：gradient 不能命名文件或主机，因此不需要拒绝。"""
    source = theme_files(
        tmp_path,
        "my-theme",
        {"theme.css": scoped("my-theme", "background:linear-gradient(#fff,#000)")},
    )

    assert external_themes.import_theme(str(source)) == "my-theme"


def test_a_tampered_theme_cannot_smuggle_image_set_after_install(tmp_path, install_root):
    """同一条规则在消费期也生效：安装后写入 image-set("https://…") 必须被拒。"""
    source = theme_files(tmp_path, "my-theme", {"theme.css": scoped("my-theme")})
    external_themes.import_theme(str(source))
    (install_root / "my-theme" / "theme.css").write_text(
        scoped("my-theme", 'background-image:image-set("https://example.invalid/x.png" 1x)'),
        encoding="utf-8",
    )

    with pytest.raises(external_themes.ExternalThemeError):
        external_themes.inline_theme_css("my-theme")


def test_the_standalone_example_still_works_after_the_refusal(tmp_path, install_root):
    """收尾正例：允许的写法（data URI + 本地资源）仍然照常安装并内嵌。"""
    source = theme_files(
        tmp_path,
        "my-theme",
        {
            "theme.css": scoped(
                "my-theme",
                'background:url(assets/bg.png);color:var(--x)',
            )
        },
    )
    (source / "assets").mkdir()
    (source / "assets" / "bg.png").write_bytes(b"\x89PNG")

    assert external_themes.import_theme(str(source)) == "my-theme"
    assert "data:image/png;base64," in external_themes.inline_theme_css("my-theme")


def test_the_checker_uses_the_shared_scanner():
    """一个扫描器、三条消费链：checker 不得自带第二套 URL 解析。"""
    source = (ROOT / "tools" / "standalone_closure.py").read_text(encoding="utf-8")

    assert "scan_references" in source
    assert "CSS_URL_PATTERN" not in source


def test_the_checker_sees_a_reference_the_old_pattern_could_not():
    """反证：带括号的合法 URL —— 旧正则看不见，共享扫描器必须看见（13 条之一）。"""
    from tools import standalone_closure

    css = 'a{background:url("https://example.invalid/a(b).png")}'
    found = standalone_closure.collect_subresources("<style>" + css + "</style>")

    assert [item["ref"] for item in found] == ["https://example.invalid/a(b).png"]


def test_the_checker_fails_the_gate_on_css_it_cannot_parse():
    """解析不了就判失败：看不见全貌的扫描器不能保证没有遗漏。"""
    from tools import standalone_closure

    found = standalone_closure.collect_subresources(
        "<style>a{background:url(x.png)}/* unclosed</style>"
    )

    assert [item["ref"] for item in found][0].startswith("css-unparseable(style)")
