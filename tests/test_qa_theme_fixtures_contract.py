"""Phase 12 GUI closeout: the two QA theme specimens stay legal and stay useful.

`samples/qa-themes/` holds the themes the GUI closeout and the release acceptance both use:

* `qa-ornamented` -- a readable theme that really uses the decoration hooks, including a local
  PNG decoration. That is the only way to prove the whole chain stays intact: local asset ->
  theme validation -> data URI inline -> standalone HTML;
* `qa-no-preview` -- a fully working theme with no `preview` block, which is what proves a
  missing preview blocks nothing: not importing, not carrying, not converting, not the reader.

They live in the repository on purpose. A generated fixture would be unreadable, and these are
the product specimens a reviewer has to be able to read.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config as core_config  # noqa: E402
from core import converter, paths, viewer_assets  # noqa: E402
from core import external_themes as core_themes  # noqa: E402

FIXTURES = ROOT / "samples" / "qa-themes"
PREVIEW_KEYS = ("background", "surface", "text", "muted", "accent", "border")


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Import the fixtures into a temporary theme root and convert into a temporary tree."""
    external = tmp_path / "assets" / "themes" / "external"
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))
    monkeypatch.setattr(core_themes, "theme_root", lambda: str(external))
    monkeypatch.setattr(paths, "config_path", lambda: str(tmp_path / "profile" / "config.json"))
    monkeypatch.setattr(core_config, "PROJECT_ROOT", str(tmp_path / "app"))
    return external


def fixture_dir(name: str) -> Path:
    directory = FIXTURES / name
    assert directory.is_dir(), "samples/qa-themes/" + name + " must exist (Phase 12 GUI closeout)"
    return directory


def preview_facts():
    """Return the preview reader, refusing to guess when the capability is missing."""
    reader = getattr(core_themes, "preview_facts", None)
    assert reader is not None, (
        "core.external_themes must expose preview_facts() (Phase 12 GUI closeout)"
    )
    return reader


@pytest.mark.parametrize("name", ["qa-ornamented", "qa-no-preview"])
def test_both_fixtures_import_as_working_themes(sandbox, name: str) -> None:
    """Importing runs the real validation, including the CSS scope audit."""
    theme_id = core_themes.import_theme(str(fixture_dir(name)))

    assert theme_id == name
    assert core_themes.validate_installed_theme(theme_id), "an imported fixture must stay valid"


def test_the_ornamented_fixture_declares_the_decoration_hooks(sandbox) -> None:
    directory = fixture_dir("qa-ornamented")
    metadata = core_themes.validate_theme_directory(str(directory))

    assert "decorations.css" in metadata["files"], (
        "the decoration hooks must be a real theme file, not a comment"
    )
    assets = directory / "assets"
    payloads = sorted(assets.glob("*.png")) if assets.is_dir() else []
    assert payloads, "the ornamented fixture must carry a local decoration asset"
    css = (directory / "decorations.css").read_text(encoding="utf-8")
    assert "url(" in css, "the decoration hooks have to reference the local asset"


def test_the_ornamented_fixture_offers_a_canonical_preview(sandbox) -> None:
    reader = preview_facts()
    core_themes.import_theme(str(fixture_dir("qa-ornamented")))

    facts = reader("qa-ornamented")

    assert facts["preview_status"] == "available"
    assert sorted(facts["preview"].keys()) == sorted(PREVIEW_KEYS)


def test_the_no_preview_fixture_blocks_nothing(sandbox) -> None:
    core_themes.import_theme(str(fixture_dir("qa-no-preview")))

    facts = preview_facts()("qa-no-preview")
    selection = core_themes.resolve_theme_selection(["qa-no-preview"])

    assert facts["preview_status"] == "missing"
    assert facts["preview"] is None
    assert selection["external_ids"] == ["qa-no-preview"], (
        "a theme without a preview must still be carryable"
    )


def test_a_document_carrying_the_ornamented_theme_inlines_its_decoration(sandbox, tmp_path) -> None:
    """The end of the chain: the local asset reaches the generated document as a data URI."""
    theme_id = core_themes.import_theme(str(fixture_dir("qa-ornamented")))
    source = tmp_path / "note.md"
    source.write_text("# 标题\n\n正文一段。\n", encoding="utf-8")
    output = tmp_path / "out" / "note.html"

    saved = converter.process_single(
        str(source),
        str(output),
        {
            "template": "modern",
            "numbering": False,
            "overwrite": True,
            "external_themes": [theme_id],
        },
    )

    assert saved is not None
    html = Path(saved).read_text(encoding="utf-8")
    assert "data:image/png;base64," in html, (
        "the theme's local decoration has to be inlined into the standalone page"
    )
    assert theme_id in html, "the carried theme must be part of the generated page"


def build_themes():
    """Return the material writer, refusing to guess when the capability is missing."""
    spec = importlib.util.spec_from_file_location(
        "qa_prepare_under_test", ROOT / "packaging" / "qa_prepare.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    writer = getattr(module, "build_themes", None)
    assert writer is not None, (
        "packaging/qa_prepare.py must copy the theme specimens into the acceptance material "
        "(Phase 12 GUI closeout)"
    )
    return writer


def test_the_acceptance_material_carries_its_own_specimens(tmp_path) -> None:
    """The reviewer imports the material's copy, so the material has to be complete.

    `samples/qa-themes/` stays the source of truth, but the run imports what `qa_prepare.py`
    wrote -- which is exactly what proves the copy kept every file, `decorations.css` and the
    local PNG included.
    """
    build_themes()(tmp_path)

    for name in ("qa-ornamented", "qa-no-preview"):
        directory = tmp_path / "主题标本" / name
        assert directory.is_dir(), "the acceptance material is missing " + name
        assert core_themes.validate_theme_directory(str(directory))["id"] == name

    assets = tmp_path / "主题标本" / "qa-ornamented" / "assets"
    assert sorted(assets.glob("*.png")), (
        "the specimen's local decoration asset has to travel with the material"
    )
