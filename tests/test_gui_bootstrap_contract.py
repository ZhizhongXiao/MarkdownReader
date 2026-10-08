"""Phase 12 GUI closeout: a GUI conversion has no builtin theme selector.

The retired product behaviour was a "template" dropdown in the output sheet: it chose the
document's builtin default theme, was persisted into `config.template`, and travelled with
every conversion request. The closeout removes it from the product while `core` keeps
accepting an internal template argument, so the rule belongs to the GUI boundary and is
locked here:

* the bridge no longer offers `get_templates()`: with no selector there is no consumer, and an
  unused method would suggest the old behaviour still exists;
* a GUI conversion always renders with `BOOTSTRAP_TEMPLATE`, the internal fallback for a
  document whose reader has no preference yet;
* a client-supplied `template` cannot win. The request key is ignored at this boundary, so an
  old page, a stale bookmarklet or a hand-written bridge call cannot resurrect the control.

The builtin registry itself is not part of this: `builtin_theme_ids()` and the theme bundle
still decide what every generated page carries.
"""

import inspect
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gui.api as gui_api  # noqa: E402
from core import config as core_config  # noqa: E402
from core import paths  # noqa: E402
from gui.api import BridgeApi  # noqa: E402


class _BackendClient:
    def __init__(self) -> None:
        self.ensured = 0
        self.requests: list[dict[str, object]] = []

    def ensure_backend(self) -> dict[str, object]:
        self.ensured += 1
        return {"protocol": 1, "id": "status", "ok": True, "result": {"pid": 10}}

    def request_convert(self, params: Mapping[str, object]) -> dict[str, object]:
        captured = dict(params)
        self.requests.append(captured)
        return {"output_path": str(captured["output_path"]), "warnings": []}

    def status(self) -> dict[str, object]:
        return {"pid": 10, "renderer_pid": None}


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Run the bridge against an injected Backend client and capture IPC parameters."""
    profile = tmp_path / "profile" / "config.json"
    monkeypatch.setattr(paths, "config_path", lambda: str(profile))
    monkeypatch.setattr(core_config, "PROJECT_ROOT", str(tmp_path / "app"))
    return _BackendClient()


def test_the_bridge_no_longer_offers_a_builtin_template_list() -> None:
    """The selector is gone, so the method that fed it has to be gone too."""
    assert not hasattr(BridgeApi, "get_templates"), (
        "the builtin conversion selector was removed: an unused get_templates() would suggest "
        "the old product behaviour still exists"
    )


def test_the_builtin_registry_and_the_bundle_are_untouched() -> None:
    """Only the GUI surface changed: every generated page still carries the builtin themes."""
    from core.viewer_assets import builtin_theme_ids

    assert builtin_theme_ids(), "the builtin theme registry must stay available"
    from gui.services.lifecycle import LifecycleStorageService

    assert callable(LifecycleStorageService.get_config), (
        "configuration reads stay in the GUI backend"
    )


def test_the_bootstrap_theme_is_a_bridge_constant() -> None:
    assert getattr(gui_api, "BOOTSTRAP_TEMPLATE", None) == "modern", (
        "the GUI boundary needs one internal bootstrap theme, not a user preference"
    )


def test_the_bridge_methods_the_page_still_uses_keep_their_shape() -> None:
    """Deleting one method is the whole API change; the rest keeps its agreed shape."""
    assert list(inspect.signature(BridgeApi.convert).parameters) == ["self", "request"]
    assert list(inspect.signature(BridgeApi.set_configs).parameters) == ["self", "overrides"]
    assert list(inspect.signature(BridgeApi.get_theme_state).parameters) == ["self"]


def test_a_gui_conversion_renders_with_the_bootstrap_theme(sandbox, tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_text("# 标题\n\n正文。\n", encoding="utf-8")

    result = BridgeApi(backend_client=sandbox).convert(
        {
            "inputs": [str(source)],
            "output_dir": str(tmp_path / "out"),
            "overwrite": True,
            "build_index": False,
        }
    )

    assert result.get("success") is not False, result
    assert sandbox.ensured == 1
    assert sandbox.requests[0]["template"] == "modern"


def test_a_client_supplied_template_cannot_override_the_bootstrap(sandbox, tmp_path: Path) -> None:
    """Old pages and hand-written requests must not be able to bring the control back."""
    source = tmp_path / "note.md"
    source.write_text("# 标题\n\n正文。\n", encoding="utf-8")

    BridgeApi(backend_client=sandbox).convert(
        {
            "inputs": [str(source)],
            "output_dir": str(tmp_path / "out"),
            "template": "office",
            "overwrite": True,
            "build_index": False,
        }
    )

    assert sandbox.requests[0]["template"] == "modern", (
        "a request-supplied template won the conversion: the GUI boundary must render with "
        "BOOTSTRAP_TEMPLATE no matter what the client sends"
    )


def test_gui_conversion_sends_each_batch_document_through_the_backend(sandbox, tmp_path: Path):
    source_root = tmp_path / "notes"
    nested = source_root / "nested"
    nested.mkdir(parents=True)
    first = source_root / "first.md"
    second = nested / "second.md"
    first.write_text("[second](nested/second.md)\n", encoding="utf-8")
    second.write_text("# Second\n", encoding="utf-8")

    result = BridgeApi(backend_client=sandbox).convert(
        {
            "inputs": [str(source_root)],
            "output_dir": str(tmp_path / "out"),
            "preserve_structure": True,
            "overwrite": True,
            "build_index": True,
        }
    )

    assert result["success"] is True
    assert sandbox.ensured == 1
    assert len(sandbox.requests) == 2
    link_map = sandbox.requests[0]["document_map"]
    assert isinstance(link_map, dict)
    assert sandbox.requests[1]["document_map"] == link_map
    assert link_map[str(first)] == str(tmp_path / "out" / "notes-HTML" / "first.html")
    assert link_map[str(second)] == str(
        tmp_path / "out" / "notes-HTML" / "nested" / "second.html"
    )
    entry_file = result.get("entry_file")
    assert isinstance(entry_file, str)
    assert Path(entry_file).is_file()
