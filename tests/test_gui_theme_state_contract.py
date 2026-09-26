"""Phase 8C: the bridge reports configured, selected and missing user themes.

A theme selection has two halves with different lifetimes. `configured` is what
config.json remembers and lives until the user changes it; `selected` is what is
installed and valid in this run. Phase 9 must be able to show the difference, otherwise
saving an unrelated setting from a form that only knows `selected` would erase the choice
of a theme the user merely uninstalled for a moment.

The validity of a theme itself is Phase 7 contract and is tested there; here the installed
themes are stubbed so this file only measures the state split.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config as core_config  # noqa: E402
from core import paths  # noqa: E402
from core.external_themes import ExternalThemeError  # noqa: E402
from gui.api import BridgeApi  # noqa: E402


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Point the profile location and the legacy location at a temporary tree."""
    profile = tmp_path / "profile" / "config.json"
    monkeypatch.setattr(paths, "config_path", lambda: str(profile))
    monkeypatch.setattr(core_config, "PROJECT_ROOT", str(tmp_path / "app"))
    return profile


def pretend_installed(monkeypatch, theme_ids):
    """Stub the installed themes in both bindings: the bridge and the resolver."""

    def installed(**kwargs):
        return list(theme_ids)

    monkeypatch.setattr("core.viewer_assets.external_theme_ids", installed)
    monkeypatch.setattr("gui.api.external_theme_ids", installed)


def pretend_valid(monkeypatch):
    """Pretend every installed theme passes Phase 7 validation."""

    def valid(theme_id, **kwargs):
        return None

    monkeypatch.setattr("core.external_themes.validate_installed_theme", valid)


@pytest.fixture()
def paper_installed(monkeypatch):
    """Pretend `paper` is installed and valid."""
    pretend_installed(monkeypatch, ["paper"])
    pretend_valid(monkeypatch)


def test_the_state_reports_a_missing_theme_without_losing_the_choice(
    sandbox, paper_installed
):
    core_config.save_config({"template": "office", "external_themes": ["paper", "ghost"]})

    state = BridgeApi().get_theme_state()

    assert state["configured"] == ["paper", "ghost"]
    assert state["installed"] == ["paper"]
    assert state["selected"] == ["paper"]
    assert state["missing"] == ["ghost"]
    assert state["default"] == "office"
    assert any("ghost" in warning for warning in state["warnings"])


def test_a_broken_installed_theme_is_reported_rather_than_hidden(sandbox, monkeypatch):
    pretend_installed(monkeypatch, ["paper"])

    def broken(theme_id, **kwargs):
        raise ExternalThemeError("外置主题 CSS 不合法：" + theme_id)

    monkeypatch.setattr("core.external_themes.validate_installed_theme", broken)
    core_config.save_config({"external_themes": ["paper"]})

    state = BridgeApi().get_theme_state()

    assert state["configured"] == ["paper"]
    assert state["selected"] == []
    assert state["missing"] == []
    assert any("不合法" in warning for warning in state["warnings"])


def test_a_deleted_default_theme_keeps_its_config_value_and_warns(sandbox, monkeypatch):
    pretend_installed(monkeypatch, [])
    core_config.save_config({"template": "ghost"})

    state = BridgeApi().get_theme_state()

    assert state["default"] == "ghost"
    assert core_config.load_config()["template"] == "ghost"
    assert any("ghost" in warning for warning in state["warnings"])


def test_set_configs_persists_the_theme_selection_through_core(
    sandbox, paper_installed, tmp_path
):
    source = tmp_path / "in"
    source.mkdir(parents=True, exist_ok=True)
    (source / "a.md").write_text("# 标题\n", encoding="utf-8")

    BridgeApi().set_configs({"input": str(source), "external_themes": ["paper"]})

    reloaded = core_config.load_config()
    assert reloaded["external_themes"] == ["paper"]
    # The GUI normalizes a picked path with forward slashes; compare as paths.
    assert Path(reloaded["input"]) == source


def test_set_configs_refuses_a_path_like_theme_id(sandbox):
    """程序内部传路径型 ID 属于调用方违约：立刻报错，不写进配置。"""
    with pytest.raises(ValueError):
        BridgeApi().set_configs({"external_themes": ["C:\\themes\\paper"]})
