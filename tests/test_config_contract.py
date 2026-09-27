"""Phase 8: the configuration model, its file, and what it must never lose.

Three properties matter, and each one has a reason:

* the write path belongs to core, so the GUI, tests and any future CLI persist the same
  shape through the same atomic writer;
* `profile/config.json` is authoritative once it exists -- a legacy file beside the
  executable must not come back to life and shadow it;
* a user theme selection survives a theme being temporarily missing: `configured` is
  what the file remembers, `selected` is what is installed right now.
"""

import builtins
import json
import logging
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


# ── Phase 10: the legacy file is an upgrade input, not a permanent fallback ────────────
#
# The reconnaissance that unblocked this phase found the hole: as long as `_find_config`
# returns the legacy file whenever the profile is missing, deleting the profile makes an old
# configuration reappear -- the user asks for "remove my data" and gets their settings back.
# Migration is therefore a one-time act with an observable end: afterwards the profile is
# authoritative and the legacy file is gone. No tombstone state is introduced for this; the
# existence of the profile is what makes it one-time.


def test_a_legacy_install_migrates_into_the_profile_and_retires_the_legacy_file(
    sandbox, monkeypatch
):
    """legacy 是可解析的升级输入：内容进 canonical sectioned profile，legacy 退场。"""
    write_json(
        sandbox["legacy"],
        {"build": {"template": "office"}, "features": {"auto_open": False}},
    )
    calls: list[dict] = []
    original = core_config.save_config

    def spy(cfg, config_path=None):
        calls.append(dict(cfg))
        return original(cfg, config_path)

    monkeypatch.setattr(core_config, "save_config", spy)

    loaded = core_config.load_config()

    assert loaded["template"] == "office"
    assert loaded["auto_open"] is False
    assert sandbox["profile"].is_file(), "the legacy values must land in profile/config.json"
    data = json.loads(sandbox["profile"].read_text(encoding="utf-8"))
    assert set(data) == {"build", "document", "features"}, data
    assert data["build"]["template"] == "office"
    assert not sandbox["legacy"].exists(), "a completed migration retires the legacy file"

    # One-time means one write: the second read finds the profile and does not migrate again.
    core_config.load_config()
    assert len(calls) == 1, calls


def test_an_existing_profile_never_consults_the_legacy_file(sandbox, caplog):
    """profile 一旦存在就是权威：legacy 连解析都不该发生，更不该被迁移。"""
    write_json(sandbox["profile"], {"build": {"template": "vscode"}})
    sandbox["legacy"].write_text("{ not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="core.config"):
        loaded = core_config.load_config()

    assert loaded["template"] == "vscode"
    assert sandbox["legacy"].exists(), "a migration must not run while a profile exists"
    assert not [
        record for record in caplog.records if str(sandbox["legacy"]) in record.getMessage()
    ], "the legacy file must not even be parsed"


def test_deleting_the_profile_cannot_resurrect_a_legacy_config(sandbox):
    """Phase 11 的前提：迁移完成后删掉 profile，旧值不得复活。

    今天的行为是反过来的 —— legacy 一直在，profile 一删，下一次 load 就把它读回来：用户会看到
    「我点了完全移除，设置却回来了」。
    """
    write_json(
        sandbox["legacy"],
        {"build": {"template": "office", "external_themes": ["paper"]}},
    )

    assert core_config.load_config()["template"] == "office"
    # `missing_ok=True`：迁移还没发生时 profile 本就不存在，而本条契约要判的是「旧值不得复活」，
    # 所以删除这一步不该掩盖真正的断言（今天的红签名正是下面返回了 office）。
    sandbox["profile"].unlink(missing_ok=True)

    fresh = core_config.load_config()

    assert fresh["template"] == core_config._DEFAULTS["template"]
    assert fresh["external_themes"] == []
    assert fresh["output"] == core_config._DEFAULTS["output"]
    assert not sandbox["legacy"].exists()
    assert not sandbox["profile"].exists(), "defaults must not write a profile of their own"


def test_a_corrupt_legacy_migrates_nothing_and_says_so(sandbox, caplog):
    """迁移失败不得制造半个 profile，也不能把坏文件当成已处理。"""
    sandbox["legacy"].write_text("{ not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="core.config"):
        loaded = core_config.load_config()

    assert loaded["template"] == core_config._DEFAULTS["template"]
    assert not sandbox["profile"].exists(), "a failed migration must not write a half profile"
    assert sandbox["legacy"].exists(), "the unreadable file stays for a retry or a cleanup"
    assert [
        record for record in caplog.records if str(sandbox["legacy"]) in record.getMessage()
    ], "the unreadable legacy file is reported"


def test_the_migration_writes_through_the_one_atomic_config_writer(sandbox, monkeypatch):
    """不创建第二套 config writer：迁移复用 `save_config()`（原子写 + sectioned 形状）。"""
    write_json(sandbox["legacy"], {"build": {"template": "office"}})
    seen: list[dict] = []
    original = core_config.save_config

    def spy(cfg, config_path=None):
        seen.append(dict(cfg))
        return original(cfg, config_path)

    monkeypatch.setattr(core_config, "save_config", spy)

    core_config.load_config()

    assert len(seen) == 1, seen
    assert "template" in seen[0], "the writer receives a configuration, not raw JSON text"
    data = json.loads(sandbox["profile"].read_text(encoding="utf-8"))
    assert data["build"]["template"] == "office"
    assert core_config.load_config()["template"] == "office"


def test_the_migration_reads_the_legacy_file_once(sandbox, monkeypatch):
    """一次性迁移只取一次快照：严格读取之后不得再读 legacy。

    两次读取之间有一个 TOCTOU 窗口 —— 第二次读到损坏内容就会把 defaults 写进 profile，然后把那份
    已确认可迁移的 legacy 删掉。这里数的是对 legacy 这个文件的真实内容读取次数（与函数名无关）。
    """
    write_json(sandbox["legacy"], {"build": {"template": "office"}})
    opened: list[str] = []
    real_open = builtins.open

    def counting_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)

    assert core_config.load_config()["template"] == "office"

    assert opened.count(str(sandbox["legacy"])) == 1, opened


def test_a_failed_retirement_is_a_warning_and_never_a_second_migration(
    sandbox, monkeypatch, caplog
):
    """retire 失败不等于迁移失败：profile 已落盘所以不会复活，但必须留下可审计的 warning。"""
    write_json(sandbox["legacy"], {"build": {"template": "office"}})

    def locked(_target):
        raise OSError(32, "the file is in use")

    monkeypatch.setattr(os, "remove", locked)

    with caplog.at_level(logging.WARNING, logger="core.config"):
        loaded = core_config.load_config()

    assert loaded["template"] == "office"
    assert sandbox["profile"].is_file(), "the values are already safe in the profile"
    assert sandbox["legacy"].exists(), "the retirement failed, so the file is still there"
    assert [
        record for record in caplog.records if str(sandbox["legacy"]) in record.getMessage()
    ], "a failed retirement is reported"

    # The profile exists now, so the surviving legacy file can never win again.
    assert core_config.load_config()["template"] == "office"


def test_an_explicit_path_never_triggers_a_migration(sandbox, tmp_path):
    """显式路径是一次性输入：它不得顺手改写用户数据，也不得让 legacy 退场。"""
    explicit = tmp_path / "explicit.json"
    write_json(explicit, {"build": {"template": "office"}})
    write_json(sandbox["legacy"], {"build": {"template": "vscode"}})

    assert core_config.load_config(str(explicit))["template"] == "office"
    assert not sandbox["profile"].exists()
    assert sandbox["legacy"].exists()


def test_a_failed_profile_write_keeps_and_uses_the_legacy_config(
    sandbox, monkeypatch, caplog
):
    """最危险的一支：profile 写不进去时，绝不能先删 legacy，也不能让可读的旧配置失效。

    升级存储失败不该把一个此前能正常读取的安装变成 defaults，更不该删掉用户唯一的那份配置。
    因此顺序被冻结为：parse → save（失败则保留 legacy，本次继续用已解析的内容）→ remove。
    """
    write_json(sandbox["legacy"], {"build": {"template": "office"}})
    removals: list[str] = []

    def disk_full(_cfg, _config_path=None):
        raise OSError(28, "disk full")

    monkeypatch.setattr(core_config, "save_config", disk_full)
    monkeypatch.setattr(os, "remove", removals.append)

    with caplog.at_level(logging.WARNING, logger="core.config"):
        loaded = core_config.load_config()

    assert loaded["template"] == "office", "a failed upgrade must not downgrade a readable config"
    assert not sandbox["profile"].exists()
    assert sandbox["legacy"].exists(), "the only copy of the user's settings must survive"
    assert removals == [], "legacy must never be deleted before the profile write succeeded"
    assert [
        record for record in caplog.records if str(sandbox["legacy"]) in record.getMessage()
    ], "the failed upgrade is reported"
