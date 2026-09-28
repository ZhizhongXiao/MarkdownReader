"""Phase 9B1: the settings surface owns installation facts, not the carry set.

The main page answers "which installed themes does this document carry"
(`BridgeApi.get_theme_state()`); the settings page answers "what is installed here and
does it still work" (`BridgeApi.get_theme_inventory()`). AGENTS section 17 keeps those
two concepts apart, so this file locks the two rules that make the separation real:

* the inventory validates every installed theme -- including one that is broken and was
  never configured, because `theme_state().invalid` only covers configured ids and
  reusing it here would report a broken installation as healthy;
* no management action may write the configuration: installing or uninstalling a theme
  is not the same act as (un)checking it, so the memory keeps the id and the main page
  reports `missing` afterwards.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gui.api as gui_api  # noqa: E402
from core import config as core_config  # noqa: E402
from core import paths  # noqa: E402
from gui.api import BridgeApi  # noqa: E402


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Install themes and configuration into a temporary tree."""
    external = tmp_path / "assets" / "themes" / "external"
    profile = tmp_path / "profile" / "config.json"
    monkeypatch.setattr(paths, "config_path", lambda: str(profile))
    monkeypatch.setattr(core_config, "PROJECT_ROOT", str(tmp_path / "app"))
    monkeypatch.setattr("core.viewer_assets.external_themes_root", lambda: str(external))
    monkeypatch.setattr("core.external_themes.theme_root", lambda: str(external))
    return external


def install_theme(root: Path, theme_id: str, *, css: str | None = None) -> Path:
    """Write a minimal but valid installed theme and return its directory."""
    directory = root / theme_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metadata.json").write_text(
        json.dumps({"id": theme_id, "name": theme_id, "files": ["theme.css"]}),
        encoding="utf-8",
    )
    (directory / "theme.css").write_text(
        css if css is not None else 'html[data-theme-id="' + theme_id + '"]{}',
        encoding="utf-8",
    )
    return directory


def test_the_settings_bridge_methods_exist_with_the_agreed_shapes():
    """桥接面形状：三个事实读取方法无参；import / export 收一个请求字典；remove 收一个 id。"""
    import inspect

    for name in ("get_theme_inventory", "get_storage_info", "get_about_info"):
        parameters = list(inspect.signature(getattr(BridgeApi, name)).parameters)
        assert parameters == ["self"], name

    for name in ("import_theme", "export_theme_template"):
        parameters = list(inspect.signature(getattr(BridgeApi, name)).parameters)
        assert parameters[:2] == ["self", "request"], name

    parameters = list(inspect.signature(BridgeApi.remove_theme).parameters)
    assert parameters == ["self", "theme_id"], parameters


def test_the_inventory_validates_every_installed_theme_not_only_the_configured_ones(sandbox):
    """9B 新发现：`invalid` 只覆盖 configured 的 id，设置页不能把它当安装健康度。

    一个已安装、被手工改坏、又从未被配置的主题，在 `theme_state()` 里既不是 `invalid`，
    也不会出现在任何其它列表里。管理页必须自己逐个跑 use-time gate，否则它会把一个坏
    安装显示成健康 —— 而用户要到下一次转换才会撞上 hard failure。
    """
    install_theme(sandbox, "paper")
    install_theme(
        sandbox,
        "damaged",
        css="<style>div{background:url(http://example.com/x.png)}</style>",
    )
    core_config.save_config({"external_themes": []})

    state = BridgeApi().get_theme_state()
    assert state["invalid"] == [], (
        "fixture: the broken theme is not configured, so it is not invalid"
    )

    inventory = BridgeApi().get_theme_inventory()

    assert inventory["root"] == str(sandbox)
    assert [row["id"] for row in inventory["installed"]] == ["damaged", "paper"]
    by_id = {row["id"]: row for row in inventory["installed"]}
    assert by_id["paper"]["valid"] is True
    assert by_id["paper"]["reason"] is None
    assert by_id["damaged"]["valid"] is False
    assert by_id["damaged"]["reason"], "why a theme cannot be used is part of the answer"


def test_no_management_action_writes_the_configuration(sandbox, monkeypatch, tmp_path):
    """安装 / 卸载 / 导出 / 打开目录都不得写 config：记忆只由主页面的勾选改变。

    卸载一个已安装的主题只删安装副本；`configured` 原样保留，于是主页把那个 id 报成
    `missing`（Phase 8C 的语义），而不是「用户删了文件，于是选择也被悄悄清掉」。
    """
    install_theme(sandbox, "paper")
    install_theme(tmp_path, "incoming")
    core_config.save_config({"external_themes": ["paper", "ghost"]})
    writes: list[dict] = []
    monkeypatch.setattr(core_config, "save_config", writes.append)
    opened: list[str] = []
    monkeypatch.setattr(gui_api.os, "startfile", opened.append, raising=False)

    api = BridgeApi()
    assert api.import_theme({"source": str(tmp_path / "incoming")})["ok"] is True
    assert api.remove_theme("paper")["ok"] is True
    assert api.export_theme_template({"destination": str(tmp_path / "exported")})["ok"] is True
    assert api.open_theme_location()["ok"] is True

    assert writes == [], "no settings-page action may persist configuration"
    assert core_config.load_config()["external_themes"] == ["paper", "ghost"], (
        "an uninstalled theme stays in the memory: it becomes missing, not forgotten"
    )
    assert not (sandbox / "paper").exists(), "the installed copy is the only thing that was removed"
    assert (sandbox / "incoming" / "metadata.json").is_file(), "the import really landed"
    assert (tmp_path / "exported" / "metadata.json").is_file(), "the template was exported for real"
    assert opened == [str(sandbox)], "opening the location goes through the system opener"


def test_open_theme_location_creates_the_directory_it_opens(sandbox, monkeypatch):
    """新环境（从未装过主题）里目录并不存在：必须是「创建后打开」，不是静默 no-op。"""
    opened: list[str] = []
    monkeypatch.setattr(gui_api.os, "startfile", opened.append, raising=False)
    assert not sandbox.exists(), "fixture: nothing has been installed yet"

    result = BridgeApi().open_theme_location()

    assert result["ok"] is True
    assert sandbox.is_dir(), "the directory the page offers to open must exist afterwards"
    assert opened == [str(sandbox)]


def test_open_theme_location_reports_a_failing_system_opener(sandbox, monkeypatch):
    """9B2：opener 失败必须和其它管理动作同形状，而不是把异常丢给页面。

    `ensure_theme_root()` 的失败早已被 shaped refusal 覆盖，但「创建成功、打开失败」这一支
    会越过边界直接抛出去。JS 能 catch rejected Promise，所以不是严重功能 bug，但桥接协议在
    这里漂了形状：设置页四个动作里只有它可能抛异常。
    """

    def refuse(_path: str) -> None:
        raise OSError("shell failed")

    monkeypatch.setattr(gui_api.os, "startfile", refuse, raising=False)

    result = BridgeApi().open_theme_location()

    assert result["ok"] is False, result
    assert result["path"] == ""
    assert result["error"], "the refusal names what went wrong"


def test_storage_info_reports_the_real_paths_for_each_packaging_mode(monkeypatch):
    """存储信息是 core.paths 的事实，不是页面或桥接层自己的猜测。"""
    monkeypatch.setattr(paths, "user_data_root", lambda: "U:/data")
    monkeypatch.setattr(paths, "config_path", lambda: "U:/data/profile/config.json")
    monkeypatch.setattr(paths, "runtime_root", lambda: "U:/data/runtime")
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    monkeypatch.setattr(paths, "is_onedir", lambda: False)

    info = BridgeApi().get_storage_info()

    assert info["mode"] == "source"
    assert info["user_data_root"] == "U:/data"
    assert info["config_path"] == "U:/data/profile/config.json"
    assert info["runtime_root"] == "U:/data/runtime"
    # The theme directory follows the (patched) user data root, so the assertion can name the
    # documented layout instead of a literal path. Which separator `core.paths` writes is its
    # business, hence the normalization -- and note that `gui.api` imports `theme_root` by
    # name, so patching `core.external_themes.theme_root` would only move the expectation,
    # never the value under test.
    assert str(info["external_themes_root"]).replace("\\", "/") == "U:/data/assets/themes/external"
    assert "runtime" in info["runtime_note"], (
        "the note still explains what the runtime directory holds"
    )

    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths, "is_onedir", lambda: True)
    assert BridgeApi().get_storage_info()["mode"] == "onedir"

    monkeypatch.setattr(paths, "is_onedir", lambda: False)
    assert BridgeApi().get_storage_info()["mode"] == "onefile"


def test_about_reports_the_single_runtime_version(monkeypatch):
    """版本只有一个运行时来源：`core.version`，由 test_version_contract 绑定到 pyproject。"""
    from core import version

    monkeypatch.setattr(paths, "is_frozen", lambda: False)

    info = BridgeApi().get_about_info()

    assert info["name"] == "MarkdownReader"
    assert info["version"] == version.__version__
    assert info["renderer_version"] == core_config.PRODUCTION_RENDERER_VERSION
    assert info["mode"] == "source"
    assert info["python"]


# ── Phase 11: the settings facts also decide whether user data may be removed ────────


def test_storage_info_offers_the_removal_only_on_onefile(monkeypatch):
    """P11-1/P11-11：capability 是 `core.paths` 的事实，页面不需要自己猜 frozen 布局。"""
    monkeypatch.setattr(paths, "user_data_root", lambda: "U:/data")

    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    monkeypatch.setattr(paths, "is_onedir", lambda: False)
    assert BridgeApi().get_storage_info()["removal_available"] is False, "source"

    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths, "is_onedir", lambda: True)
    assert BridgeApi().get_storage_info()["removal_available"] is False, "onedir"

    monkeypatch.setattr(paths, "is_onedir", lambda: False)
    info = BridgeApi().get_storage_info()

    assert info["removal_available"] is True, "onefile"
    assert [item["key"] for item in info["removal_items"]] == [
        "config",
        "external-themes",
        "runtime",
    ]
    for item in info["removal_items"]:
        assert item["label"], item
        assert item["path"], item


def test_the_removal_items_follow_the_path_facts(monkeypatch):
    """三项事实来自解析器：改 `core.paths` 就跟着改，桥接不得写死路径。"""
    monkeypatch.setattr(paths, "user_data_root", lambda: "U:/data")
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths, "is_onedir", lambda: False)

    items = {
        item["key"]: str(item["path"]).replace("\\", "/")
        for item in BridgeApi().get_storage_info()["removal_items"]
    }

    assert items["config"] == "U:/data/profile/config.json"
    assert items["external-themes"] == "U:/data/assets"
    assert items["runtime"] == "U:/data/runtime"


def test_the_runtime_note_no_longer_promises_a_missing_action(monkeypatch):
    """Phase 11 落地后「仍未提供」成为陈旧事实：说明必须改述真实边界。"""
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths, "is_onedir", lambda: False)

    note = BridgeApi().get_storage_info()["runtime_note"]

    assert "仍未提供" not in note, note
    assert "onefile" in note, "the note says where removing user data exists: " + note


def test_the_removal_bridge_call_has_the_agreed_shape(monkeypatch):
    """桥接名与形状冻结：无参请求 + 一个 {ok, error} 回复（与设置页动作同一协议）。"""
    import inspect

    method = getattr(BridgeApi, "request_user_data_removal", None)
    assert method is not None, "BridgeApi must offer request_user_data_removal()"
    parameters = list(inspect.signature(method).parameters)
    assert parameters == ["self"], parameters

    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    refused = method(BridgeApi())

    assert isinstance(refused, dict), refused
    assert refused.get("ok") is False, refused
    assert refused.get("error"), refused
