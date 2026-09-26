"""Phase 8: the configuration model, its file, and what it must never lose.

Three properties matter, and each one has a reason:

* the write path belongs to core, so the GUI, tests and any future CLI persist the same
  shape through the same atomic writer;
* `profile/config.json` is authoritative once it exists -- a legacy file beside the
  executable must not come back to life and shadow it;
* a user theme selection survives a theme being temporarily missing: `configured` is
  what the file remembers, `selected` is what is installed right now.
"""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config as core_config  # noqa: E402
from core import paths  # noqa: E402


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Point the profile location and the legacy location at a temporary tree."""
    profile = tmp_path / "profile" / "config.json"
    legacy = tmp_path / "app" / core_config.CONFIG_FILENAME
    legacy.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths, "config_path", lambda: str(profile))
    monkeypatch.setattr(core_config, "PROJECT_ROOT", str(legacy.parent))
    return {"profile": profile, "legacy": legacy, "root": tmp_path}


def test_an_explicit_path_wins_over_every_location(sandbox, tmp_path):
    explicit = tmp_path / "explicit.json"
    write_json(explicit, {"build": {"template": "office"}})
    write_json(sandbox["profile"], {"build": {"template": "vscode"}})

    assert core_config.load_config(str(explicit))["template"] == "office"


def test_profile_wins_over_the_legacy_file(sandbox):
    write_json(sandbox["legacy"], {"build": {"template": "vscode"}})
    write_json(sandbox["profile"], {"build": {"template": "office"}})

    assert core_config.load_config()["template"] == "office"


def test_a_broken_profile_does_not_resurrect_the_legacy_file(sandbox):
    """profile 一旦存在就是权威：它坏了也不能偷偷回落 legacy。"""
    write_json(sandbox["legacy"], {"build": {"template": "vscode"}})
    sandbox["profile"].parent.mkdir(parents=True, exist_ok=True)
    sandbox["profile"].write_text("{ not json", encoding="utf-8")

    assert core_config.load_config()["template"] == core_config._DEFAULTS["template"]


def test_a_legacy_only_install_still_reads(sandbox):
    write_json(sandbox["legacy"], {"build": {"template": "office"}})

    assert core_config.load_config()["template"] == "office"


def test_save_writes_profile_and_the_next_load_reads_it(sandbox):
    write_json(sandbox["legacy"], {"build": {"template": "vscode"}})

    written = core_config.save_config({"template": "office", "external_themes": ["paper"]})

    assert Path(written) == sandbox["profile"]
    assert sandbox["profile"].is_file()
    reloaded = core_config.load_config()
    assert reloaded["template"] == "office"
    assert reloaded["external_themes"] == ["paper"]
    assert not sandbox["legacy"].with_name("config.json").samefile(sandbox["profile"])


def test_save_keeps_the_previous_file_when_the_replace_fails(sandbox, monkeypatch):
    write_json(sandbox["profile"], {"build": {"template": "vscode"}})
    before = sandbox["profile"].read_bytes()

    def broken_replace(source, target):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)

    with pytest.raises(OSError):
        core_config.save_config({"template": "office"})

    assert sandbox["profile"].read_bytes() == before, "旧配置必须逐字节保留"
    leftovers = [name for name in os.listdir(sandbox["profile"].parent) if name != "config.json"]
    assert leftovers == [], leftovers


def test_save_persists_only_the_fields_that_have_persistence_semantics(sandbox):
    """不要把 _DEFAULTS 整体落盘：title / overwrite 目前没有持久化语义。"""
    core_config.save_config(
        {"template": "office", "title": "我的文档", "overwrite": True, "external_themes": []}
    )

    data = json.loads(sandbox["profile"].read_text(encoding="utf-8"))
    assert "title" not in json.dumps(data, ensure_ascii=False)
    assert "overwrite" not in data.get("features", {})
    assert data["build"]["template"] == "office"
    assert data["build"]["external_themes"] == []


def test_save_refuses_a_path_like_theme_id(sandbox):
    """config 只存 ID，永不存路径；程序内部传错就直接报错。"""
    with pytest.raises(ValueError):
        core_config.save_config({"external_themes": ["C:/themes/paper"]})

    with pytest.raises(ValueError):
        core_config.save_config({"external_themes": ["paper/../academic"]})


def test_reading_drops_invalid_entries_without_failing(sandbox):
    """用户手改的 JSON 里一个坏条目不该阻止启动：丢弃 + 记 warning。"""
    write_json(
        sandbox["profile"],
        {"build": {"external_themes": ["paper", "", "  paper  ", 7, "C:/x", "academic"]}},
    )

    assert core_config.load_config()["external_themes"] == ["paper", "academic"]


def test_the_two_theme_concepts_stay_independent(sandbox):
    """template = 文档默认主题；external_themes = 额外携带列表；两者互不影响。"""
    core_config.save_config({"template": "office", "external_themes": ["paper"]})

    data = json.loads(sandbox["profile"].read_text(encoding="utf-8"))
    assert data["build"]["template"] == "office"
    assert data["build"]["external_themes"] == ["paper"]
    assert core_config.load_config()["template"] == "office"


def test_a_missing_theme_stays_in_the_configuration(sandbox):
    """主题暂时不存在时不得从配置里抹掉用户的选择（AGENTS 17）。"""
    core_config.save_config({"external_themes": ["ghost"]})

    assert core_config.load_config()["external_themes"] == ["ghost"]
