"""Phase 12 GUI closeout: a theme's static preview is optional metadata, never validity.

The GUI has to answer "what does this theme look like" before any document exists, and it must
do that without running user CSS. The closeout therefore adds a small optional `preview` block
to `metadata.json` -- six colour tokens, nothing more -- plus preview facts that stay strictly
separate from whether the theme itself works:

    preview:        {...} | None
    preview_status: available | missing | invalid
    preview_reason: "" | why

Two rules are the point of this file:

* a theme without a preview, or with a broken one, is still a healthy theme: it validates, it
  can be carried, and it converts. `valid` / `invalid` keep meaning exactly what the
  external-theme CSS contract says, and nothing else;
* the schema stays canonical: six keys, `#rgb` / `#rrggbb` values, nothing extra. A preview is
  a convenience for the GUI, so a typo makes the preview unavailable -- not the theme.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import external_themes as core_themes  # noqa: E402
from core import paths, viewer_assets  # noqa: E402
from gui.api import BridgeApi  # noqa: E402

OMIT = object()

VALID_PREVIEW = {
    "background": "#f2eee5",
    "surface": "#fffdf8",
    "text": "#302b25",
    "muted": "#81776b",
    "accent": "#956439",
    "border": "#d6c6b2",
}


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Install themes into a temporary tree so nothing touches the real profile."""
    external = tmp_path / "assets" / "themes" / "external"
    monkeypatch.setattr(viewer_assets, "external_themes_root", lambda: str(external))
    monkeypatch.setattr(core_themes, "theme_root", lambda: str(external))
    monkeypatch.setattr(paths, "config_path", lambda: str(tmp_path / "profile" / "config.json"))
    return external


def install(root: Path, theme_id: str, preview=OMIT) -> Path:
    """Write a valid theme whose preview metadata is whatever the case needs."""
    directory = root / theme_id
    directory.mkdir(parents=True, exist_ok=True)
    metadata = {"id": theme_id, "name": theme_id, "files": ["theme.css"]}
    if preview is not OMIT:
        metadata["preview"] = preview
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (directory / "theme.css").write_text(
        'html[data-theme-id="' + theme_id + '"]{}', encoding="utf-8"
    )
    return directory


def preview_facts():
    """Return the preview reader, refusing to guess when the capability is missing."""
    reader = getattr(core_themes, "preview_facts", None)
    assert reader is not None, (
        "core.external_themes must expose preview_facts() (Phase 12 GUI closeout)"
    )
    return reader


def test_a_theme_without_a_preview_reports_missing(sandbox) -> None:
    install(sandbox, "plain")

    facts = preview_facts()("plain")

    assert facts["preview"] is None
    assert facts["preview_status"] == "missing"
    assert facts["preview_reason"], "a missing preview needs a reason the GUI can show"


def test_a_valid_preview_is_reported_with_its_tokens(sandbox) -> None:
    install(sandbox, "ornamented", dict(VALID_PREVIEW))

    facts = preview_facts()("ornamented")

    assert facts["preview_status"] == "available"
    assert facts["preview_reason"] == ""
    assert facts["preview"] == VALID_PREVIEW


def test_a_malformed_preview_does_not_touch_the_theme_itself(sandbox) -> None:
    """The point of the model: a broken preview is a GUI inconvenience, not a broken theme."""
    broken = dict(VALID_PREVIEW)
    broken["accent"] = "burnt orange"
    directory = install(sandbox, "typo-palette", broken)

    assert core_themes.validate_installed_theme("typo-palette") == str(directory), (
        "the external-theme CSS contract still decides validity"
    )
    selection = core_themes.resolve_theme_selection(["typo-palette"])
    assert selection["external_ids"] == ["typo-palette"], (
        "a theme with a broken preview must still be carryable and convertible"
    )

    facts = preview_facts()("typo-palette")
    assert facts["preview_status"] == "invalid"
    assert facts["preview"] is None
    assert facts["preview_reason"]


@pytest.mark.parametrize(
    "label, preview",
    [
        ("unknown key", dict(VALID_PREVIEW, shadow="#000000")),
        ("missing key", {key: value for key, value in VALID_PREVIEW.items() if key != "border"}),
        ("not a colour", dict(VALID_PREVIEW, text="black")),
        ("empty value", dict(VALID_PREVIEW, muted="")),
        ("not an object", ["#ffffff"]),
    ],
)
def test_the_preview_schema_is_canonical(sandbox, label: str, preview) -> None:
    install(sandbox, "shape", preview)

    facts = preview_facts()("shape")

    assert facts["preview_status"] == "invalid", label
    assert facts["preview"] is None, label


def test_theme_state_reports_preview_facts_for_installed_themes(sandbox) -> None:
    install(sandbox, "ornamented", dict(VALID_PREVIEW))
    install(sandbox, "plain")

    state = core_themes.theme_state([])

    previews = state.get("previews")
    assert isinstance(previews, dict), "theme_state() must expose preview facts per installed id"
    assert previews["ornamented"]["preview_status"] == "available"
    assert previews["plain"]["preview_status"] == "missing"
    assert state["invalid"] == [], "preview metadata never makes a theme invalid"


def test_the_bridge_passes_preview_facts_to_the_page(sandbox) -> None:
    install(sandbox, "ornamented", dict(VALID_PREVIEW))

    payload = BridgeApi().get_theme_state()

    previews = payload.get("previews")
    assert isinstance(previews, dict), (
        "get_theme_state() must hand the page the preview tokens: the GUI never reads theme files"
    )
    assert previews["ornamented"]["preview"] == VALID_PREVIEW
