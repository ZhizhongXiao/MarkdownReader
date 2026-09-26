"""Phase 8C: the bridge reports configured, selected, missing and invalid themes.

A theme selection has three different lifetimes and Phase 9 needs all of them:

* ``configured`` -- what config.json remembers; nothing done in another window or on
  another day may silently prune it;
* ``selected``   -- the subset that is installed and passes the Phase 7 use-time gate
  right now, in the configured order (not the bundle's sorted order);
* ``missing`` / ``invalid`` -- why the rest cannot be restored today. A theme that is
  gone and a theme that is present but broken are different states in the reader's UI,
  and Phase 9 should not have to infer which is which from warning text.

The first cases stub the registry so the aggregation itself is measured. The default
cases use a real installed theme and real CSS, because "the directory exists" is not
the same question as "this theme is usable as a document default".
"""

import json
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


def pretend_registry(monkeypatch, installed, *, broken=()):
    """Stub the registry and the use-time gate: ids in ``broken`` fail validation."""
    ids = list(installed)
    monkeypatch.setattr("core.viewer_assets.external_theme_ids", lambda **kwargs: list(ids))

    def validate(theme_id, **kwargs):
        if theme_id in broken:
            raise ExternalThemeError("外置主题 CSS 不合法：" + theme_id)
        return None

    monkeypatch.setattr("core.external_themes.validate_installed_theme", validate)


def test_every_configured_theme_is_classified_on_its_own(sandbox, monkeypatch):
    """一个坏主题既不能清掉它前面的 valid，也不能阻止它后面的 valid。"""
    pretend_registry(monkeypatch, ["paper", "broken", "academic"], broken={"broken"})
    core_config.save_config(
        {"template": "office", "external_themes": ["paper", "ghost", "broken", "academic"]}
    )

    state = BridgeApi().get_theme_state()

    assert state["configured"] == ["paper", "ghost", "broken", "academic"]
    assert state["installed"] == ["academic", "broken", "paper"]
    assert state["selected"] == ["paper", "academic"]
    assert state["missing"] == ["ghost"]
    assert state["invalid"] == ["broken"]
    assert any("ghost" in warning for warning in state["warnings"])
    assert any("broken" in warning for warning in state["warnings"])


def test_a_broken_installed_theme_is_reported_rather_than_hidden(sandbox, monkeypatch):
    pretend_registry(monkeypatch, ["paper"], broken={"paper"})
    core_config.save_config({"external_themes": ["paper"]})

    state = BridgeApi().get_theme_state()

    assert state["configured"] == ["paper"]
    assert state["selected"] == []
    assert state["missing"] == []
    assert state["invalid"] == ["paper"]
    assert any("不合法" in warning for warning in state["warnings"])


def test_a_deleted_default_theme_keeps_its_config_value_and_warns(sandbox, monkeypatch):
    pretend_registry(monkeypatch, [])
    core_config.save_config({"template": "ghost"})

    state = BridgeApi().get_theme_state()

    assert state["default"] == "ghost"
    assert core_config.load_config()["template"] == "ghost"
    assert any("ghost" in warning for warning in state["warnings"])


def test_a_default_theme_whose_css_broke_is_reported_and_kept(sandbox, tmp_path, monkeypatch):
    """存在 != 可用：已安装但过不了 use-time gate 的默认主题必须被报出来。"""
    root = tmp_path / "external"
    directory = root / "paper"
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        json.dumps({"id": "paper", "name": "Paper", "files": ["theme.css"]}),
        encoding="utf-8",
    )
    (directory / "theme.css").write_text(
        'html[data-theme-id="paper"]{}', encoding="utf-8"
    )
    monkeypatch.setattr("core.viewer_assets.external_themes_root", lambda: str(root))
    core_config.save_config({"template": "paper", "external_themes": []})
    # 安装之后目录被改坏：Phase 7 的 use-time gate 必须在这里被问到。
    tampered = 'html[data-theme-id="paper"]{'
    tampered += 'background-image:image-set("https://e.invalid/x.png" 1x)}'
    (directory / "theme.css").write_text(tampered, encoding="utf-8")

    state = BridgeApi().get_theme_state()

    assert state["default"] == "paper"
    assert core_config.load_config()["template"] == "paper"
    assert state["configured"] == []
    assert state["selected"] == []
    assert any("paper" in warning for warning in state["warnings"])


def test_a_default_theme_that_is_not_selectable_warns(sandbox, monkeypatch):
    """``base`` 存在但不是可选主题：装配期会失败，状态 API 必须现在就说出来。"""
    pretend_registry(monkeypatch, [])
    core_config.save_config({"template": "base"})

    state = BridgeApi().get_theme_state()

    assert state["default"] == "base"
    assert core_config.load_config()["template"] == "base"
    assert any("base" in warning for warning in state["warnings"])


def test_the_state_read_never_prunes_the_configuration(sandbox, monkeypatch):
    pretend_registry(monkeypatch, ["paper"])
    core_config.save_config({"external_themes": ["paper", "ghost"]})

    BridgeApi().get_theme_state()

    assert core_config.load_config()["external_themes"] == ["paper", "ghost"]


def test_set_configs_persists_the_theme_selection_through_core(
    sandbox, monkeypatch, tmp_path
):
    pretend_registry(monkeypatch, ["paper"])
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
