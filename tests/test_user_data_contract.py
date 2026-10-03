"""Phase 11: removing MarkdownReader user data is a terminal, application-level act.

The rule this file locks is a split of responsibility:

* `core.user_data` owns *what* user data is and *how* it goes away, and it learns every path
  from `core.paths` / `core.config` -- never from `%LOCALAPPDATA%` or `sys.frozen` itself;
* `BridgeApi` owns *ending* the session: it refuses to start while anything is still writing,
  then sets the terminal flag and destroys the window;
* `gui/app.py` owns the *order*: with the window gone and the file log closed, it deletes, and
  nothing recreates what was deleted before the process exits.

Why it cannot happen in the bridge: the WebView2 profile lives in `runtime/WebView2` and the
root logger holds `runtime/MarkdownReader.log`, so deleting while the window is alive would
fight a live browser for its own files.

Every case imports `core.user_data` lazily, the way `test_paths_contract` looks up resolvers by
name, so a module that does not exist yet fails its own case instead of breaking collection.
"""

import logging
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config as core_config  # noqa: E402
from core import paths  # noqa: E402


def user_data():
    """Return `core.user_data`, failing this case while the module does not exist yet."""
    import importlib

    return importlib.import_module("core.user_data")


def legacy_config_path() -> str:
    """Return the compatibility residue path, which `core.config` owns.

    Looked up by name, like every other Phase 11 capability in this file: a resolver that does
    not exist yet fails its own case with its own message instead of a bare AttributeError, and
    the red phase stays statically clean for a reason the reviewer can check.
    """
    resolver = getattr(core_config, "legacy_config_path", None)
    assert resolver is not None, "core.config must expose legacy_config_path()"
    return str(resolver())


def under(candidate: str, parent: str) -> bool:
    """Return True when `candidate` is inside `parent`."""
    candidate_path = os.path.abspath(candidate)
    parent_path = os.path.abspath(parent)
    return candidate_path == parent_path or candidate_path.startswith(parent_path + os.sep)


def freeze_onefile(monkeypatch, tmp_path) -> Path:
    """Make `core.paths` report a onefile build whose user data root is under tmp_path."""
    install = tmp_path / "install"
    install.mkdir(exist_ok=True)
    extraction = tmp_path / "_MEI11"
    extraction.mkdir(exist_ok=True)
    local = tmp_path / "LocalAppData"
    local.mkdir(exist_ok=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraction), raising=False)
    monkeypatch.setattr(sys, "executable", str(install / "MarkdownReader.exe"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local / "MarkdownReader"


@pytest.fixture()
def onefile_tree(tmp_path, monkeypatch):
    """A onefile user data tree with all three roots in use, plus the legacy residue.

    The legacy file is written beside the (installed) executable, which is where Phase 10
    leaves it whenever migration could not finish: an unreadable file, or a failed removal.
    """
    data = freeze_onefile(monkeypatch, tmp_path)
    (data / "profile").mkdir(parents=True)
    (data / "profile" / "config.json").write_text(
        '{"build": {"template": "office"}}', encoding="utf-8"
    )
    theme = data / "assets" / "themes" / "external" / "paper"
    theme.mkdir(parents=True)
    (theme / "theme.css").write_text("html{}", encoding="utf-8")
    (data / "runtime" / "WebView2").mkdir(parents=True)
    (data / "runtime" / paths.LOG_FILENAME).write_text("log\n", encoding="utf-8")

    app = tmp_path / "install"
    exe = app / "MarkdownReader.exe"
    exe.write_bytes(b"MZ")
    legacy = app / "config.json"
    legacy.write_text('{"build": {"template": "office"}}', encoding="utf-8")
    monkeypatch.setattr(core_config, "PROJECT_ROOT", str(app))

    assert under(str(data), str(tmp_path)), "fixture: the data root is inside the temporary tree"
    return {
        "data": data,
        "app": app,
        "exe": exe,
        "legacy": legacy,
        "profile": data / "profile",
        "assets": data / "assets",
        "runtime": data / "runtime",
    }


class WindowStub:
    """The little bit of `webview.Window` the bridge is allowed to touch."""

    def __init__(self) -> None:
        self.destroyed = 0

    def destroy(self) -> None:
        self.destroyed += 1

    def evaluate_js(self, _script: str) -> None:
        return None


class RemovalBridge:
    """The Phase 11 surface of `BridgeApi`, with the two new calls asserted explicitly.

    Everything else is forwarded, so a case can drive the ordinary bridge methods while the
    removal surface is still missing -- and the failure it reports is the missing capability,
    named, rather than an AttributeError from the test's own plumbing.
    """

    def __init__(self, api) -> None:
        self.api = api

    def request_user_data_removal(self) -> dict:
        method = getattr(self.api, "request_user_data_removal", None)
        assert method is not None, "BridgeApi must offer request_user_data_removal()"
        reply = method()
        assert isinstance(reply, dict), reply
        return reply

    def removal_requested(self) -> bool:
        method = getattr(self.api, "_should_remove_user_data_on_exit", None)
        assert method is not None, "BridgeApi must expose the removal lifecycle seam"
        return bool(method())

    def __getattr__(self, name: str) -> Any:
        return getattr(self.api, name)


def bridge_with_window() -> tuple[RemovalBridge, WindowStub]:
    """Return a `BridgeApi` (through the removal adapter) with a stub window attached."""
    from gui.api import BridgeApi

    api = BridgeApi()
    window = WindowStub()
    api.attach_window(window)
    return RemovalBridge(api), window


# ── onefile only ────────────────────────────────────────────────────────────────────


def test_removal_is_offered_only_for_a_onefile_build(monkeypatch, tmp_path):
    """source / onedir 没有这个动作：onedir 的承诺仍是「删掉整个目录即完整移除」。"""
    module = user_data()

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert module.removal_available() is False, "source has no removal action"

    app = tmp_path / "MarkdownReader"
    (app / "_internal").mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(app / "_internal"), raising=False)
    monkeypatch.setattr(sys, "executable", str(app / "MarkdownReader.exe"), raising=False)
    assert paths.is_onedir(), "fixture: this is the onedir layout"
    assert module.removal_available() is False, "onedir keeps its own promise, not a button"

    freeze_onefile(monkeypatch, tmp_path)
    assert module.removal_available() is True


# ── what user data is ───────────────────────────────────────────────────────────────


def test_the_deletion_set_is_the_path_facts_plus_the_legacy_residue(onefile_tree):
    """删除集合来自 core.paths（+ config 的 legacy resolver），不是这个模块里的字面量。"""
    module = user_data()

    targets = {os.path.abspath(target) for target in module.removal_targets()}

    assert targets == {
        os.path.abspath(paths.profile_root()),
        os.path.abspath(paths.assets_root()),
        os.path.abspath(paths.runtime_root()),
        os.path.abspath(legacy_config_path()),
    }
    assert os.path.abspath(paths.user_data_root()) not in targets, (
        "the user data root is not a recursive target: it is only removed when it is empty"
    )


def test_the_promised_items_are_the_three_facts_the_confirmation_shows(onefile_tree):
    """确认框列的三项与后端事实同源：config / external themes / runtime data。"""
    module = user_data()

    items = module.removal_items()

    assert [item["key"] for item in items] == ["config", "external-themes", "runtime"]
    paths_by_key = {item["key"]: os.path.abspath(item["path"]) for item in items}
    assert paths_by_key["config"] == os.path.abspath(paths.config_path())
    assert paths_by_key["external-themes"] == os.path.abspath(paths.assets_root())
    assert paths_by_key["runtime"] == os.path.abspath(paths.runtime_root())
    for item in items:
        assert item.get("label"), item


def test_the_executable_and_the_bundle_are_never_a_target(onefile_tree):
    """P11-8：EXE 与只读 bundle 永不进入删除集合。"""
    module = user_data()

    targets = [os.path.abspath(target) for target in module.removal_targets()]
    exe = os.path.abspath(str(onefile_tree["exe"]))

    assert exe not in targets
    assert os.path.abspath(paths.application_dir()) not in targets
    assert os.path.abspath(paths.bundle_root()) not in targets
    for target in targets:
        assert not under(exe, target), target + " would delete the executable"
    assert not any(under(target, paths.bundle_root()) for target in targets)


# ── failures are reported, never claimed away ───────────────────────────────────────


def test_a_refused_deletion_is_reported_and_retried_with_a_bound(onefile_tree, monkeypatch):
    """P11-9：删不掉就是删不掉 —— 命名失败、绝不谎报、重试有上界。"""
    module = user_data()

    def refused(*_args, **_kwargs):
        raise OSError(32, "the file is in use")

    monkeypatch.setattr(shutil, "rmtree", refused)
    monkeypatch.setattr(os, "remove", refused)
    monkeypatch.setattr(os, "unlink", refused)
    monkeypatch.setattr(os, "rmdir", refused)
    # The retry is bounded by a deadline, so the clock is what this contract moves: a recorder
    # that never advances time would spin for the full deadline of every target.
    sleeps: list[float] = []
    clock = {"now": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(time, "sleep", record_sleep)

    report = module.remove_user_data()

    assert report["ok"] is False, "a refused removal must not be reported as done"
    assert report["failed"], "the failure has to be named"
    for entry in report["failed"]:
        assert entry.get("path"), entry
        assert entry.get("error"), entry
    assert onefile_tree["profile"].is_dir(), "nothing pretends to have happened"
    assert sleeps, "a locked path is retried instead of failing on the first attempt"
    assert len(sleeps) <= 100, "the retry has a bound instead of looping forever"


def test_a_root_that_keeps_a_leftover_is_a_partial_failure(onefile_tree, monkeypatch):
    """root 不是递归目标，但它必须真的空掉：Phase 11 的验收是「不存在或为空」。"""
    module = user_data()
    leftover = onefile_tree["data"] / "unknown.tmp"
    leftover.write_text("left", encoding="utf-8")
    # This failure is permanent, so the deadline would only make the case slow: move the clock
    # the retry reads rather than reaching into the retry's own constants.
    clock = {"now": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    def jump(seconds: float) -> None:
        clock["now"] += seconds

    monkeypatch.setattr(time, "sleep", jump)

    report = module.remove_user_data()

    assert report["ok"] is False, report
    assert report["user_data_root_removed"] is False
    assert not onefile_tree["profile"].exists(), "the rest of the removal still happened"
    assert not onefile_tree["runtime"].exists()
    assert leftover.is_file(), "an unrecognised leftover is reported, not deleted blindly"
    failed_paths = [os.path.abspath(str(entry["path"])) for entry in report["failed"]]
    assert os.path.abspath(str(onefile_tree["data"])) in failed_paths, report
    for entry in report["failed"]:
        assert entry["error"], entry


def test_a_missing_target_is_a_no_op_not_a_failure(onefile_tree):
    """空安装同样可以被移除：缺失的目标不是错误，报告里不该出现 failure。"""
    module = user_data()
    shutil.rmtree(onefile_tree["assets"])
    onefile_tree["legacy"].unlink()

    report = module.remove_user_data()

    assert report["ok"] is True, report
    assert report["failed"] == []
    assert not onefile_tree["profile"].exists()
    assert not onefile_tree["runtime"].exists()
    assert not onefile_tree["data"].exists()


def build_layout(monkeypatch, tmp_path, mode: str) -> Path:
    """Build a user data tree for `mode` so a deletion attempt would have something to delete."""
    if mode == "source":
        root = tmp_path
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(paths, "source_root", lambda: str(tmp_path))
        monkeypatch.setattr(core_config, "PROJECT_ROOT", str(tmp_path))
        data = tmp_path / ".runtime"
    else:
        app = tmp_path / "MarkdownReader"
        (app / "_internal").mkdir(parents=True)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(app / "_internal"), raising=False)
        monkeypatch.setattr(sys, "executable", str(app / "MarkdownReader.exe"), raising=False)
        monkeypatch.setattr(core_config, "PROJECT_ROOT", str(app))
        root = app
        data = app / "data"

    for name in ("profile", "assets", "runtime"):
        (data / name).mkdir(parents=True)
        (data / name / "content.txt").write_text("user data", encoding="utf-8")
    (root / "config.json").write_text('{"build": {"template": "office"}}', encoding="utf-8")
    return data


@pytest.mark.parametrize("mode", ["source", "onedir"])
def test_the_deletion_refuses_a_layout_it_does_not_offer(monkeypatch, tmp_path, mode):
    """onefile-only 是 core 自己的安全前提，不是调用者的责任。

    The bridge already refuses outside onefile, which is why nothing broke: the point is that a
    destructive owner must not delegate its most important precondition upward. A source tree or an
    onedir install is left completely alone, even when the caller asks directly.
    """
    module = user_data()
    build_layout(monkeypatch, tmp_path, mode)
    calls: list[str] = []

    def spy(*_args, **_kwargs):
        calls.append("called")

    monkeypatch.setattr(shutil, "rmtree", spy)
    monkeypatch.setattr(os, "remove", spy)
    monkeypatch.setattr(os, "unlink", spy)
    monkeypatch.setattr(os, "rmdir", spy)

    report = module.remove_user_data()

    assert report["ok"] is False, report
    assert report.get("error"), report
    assert report["removed"] == []
    assert calls == [], "an unsupported layout must not touch the filesystem: " + mode


def test_a_successful_removal_leaves_nothing_behind(onefile_tree):
    """P11-6/P11-7：profile / assets / runtime 与 legacy 残留都消失，空 root 也一并消失。"""
    module = user_data()

    report = module.remove_user_data()

    assert report["ok"] is True, report
    assert not onefile_tree["profile"].exists()
    assert not onefile_tree["assets"].exists()
    assert not onefile_tree["runtime"].exists()
    assert not onefile_tree["legacy"].exists(), "the compatibility residue goes too"
    assert not onefile_tree["data"].exists(), "an empty user data root is removed as well"
    assert onefile_tree["exe"].is_file(), "the executable stays"


@pytest.mark.parametrize("residue", ['{ not json', '{"build": {"template": "office"}}'])
def test_the_legacy_residue_is_removed_whatever_left_it_behind(onefile_tree, residue):
    """corrupt 残留与 retire 失败残留都是兼容残留（P11-7），两种都必须清掉。"""
    module = user_data()
    onefile_tree["legacy"].write_text(residue, encoding="utf-8")

    report = module.remove_user_data()

    assert report["ok"] is True, report
    assert not onefile_tree["legacy"].exists(), residue


def test_the_bridge_only_requests_and_never_deletes(onefile_tree, monkeypatch):
    """P11-4：bridge 只结束会话；WebView2 还活着时它不碰任何文件。"""
    module = user_data()
    deleted: list[str] = []

    def spy():
        deleted.append("called")
        return {"ok": True}

    monkeypatch.setattr(module, "remove_user_data", spy)
    api, window = bridge_with_window()

    api.request_user_data_removal()

    assert deleted == [], "the bridge must not delete while the window is alive"
    assert window.destroyed == 1, "the request ends the window"
    assert api.removal_requested() is True
    assert onefile_tree["profile"].is_dir(), "nothing on disk changed yet"


def test_an_accepted_request_marks_once_and_destroys_once(onefile_tree):
    """accepted：终止标志只置一次、destroy 只调用一次，第二次请求被拒。"""
    api, window = bridge_with_window()

    first = api.request_user_data_removal()
    second = api.request_user_data_removal()

    assert first.get("ok") is not False, first
    assert second.get("ok") is False, second
    assert second.get("error"), "a refusal names its reason"
    assert api.removal_requested() is True
    assert window.destroyed == 1, "the window is destroyed exactly once"


def test_a_window_that_cannot_be_destroyed_is_an_explicit_refusal(onefile_tree, monkeypatch):
    """destroy 失败必须是一次被拒的请求，而不是一个既不退出也不删除的锁死会话。

    The request promises a deletion that happens after the GUI loop returns. If the window refuses
    to close, that loop never returns: accepting the request would reserve the terminal state for a
    promise nothing can keep. The refusal keeps the same shape as every other one, so the page's
    existing recovery path (GR7) unlocks it without any new front-end work.
    """
    import gui.api as gui_api

    module = user_data()
    deleted: list[str] = []

    def spy_remove():
        deleted.append("called")
        return {"ok": True}

    monkeypatch.setattr(module, "remove_user_data", spy_remove)

    class StubbornWindow(WindowStub):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def destroy(self) -> None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("close failed")
            super().destroy()

    raw = gui_api.BridgeApi()
    window = StubbornWindow()
    raw.attach_window(window)
    api = RemovalBridge(raw)

    refused = api.request_user_data_removal()

    assert refused.get("ok") is False, refused
    assert refused.get("error"), refused
    assert api.removal_requested() is False, "a refused request must not stay reserved"
    assert deleted == [], "no deletion may start without a closed window"

    accepted = api.request_user_data_removal()

    assert accepted.get("ok") is not False, accepted
    assert window.calls == 2, "the retry really tries to close the window again"
    assert window.destroyed == 1
    assert api.removal_requested() is True


def test_the_removal_is_refused_where_it_is_not_offered(monkeypatch, tmp_path):
    """source / onedir 上桥接也必须拒绝：前端不展示，不等于后端可以接受。"""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    api, window = bridge_with_window()

    refused = api.request_user_data_removal()

    assert refused.get("ok") is False, refused
    assert refused.get("error"), refused
    assert window.destroyed == 0, "no window may be destroyed for an unsupported mode"
    assert api.removal_requested() is False


# ── the terminal state refuses every writer ─────────────────────────────────────────


MUTATING_CALLS = {
    "set_configs": lambda api: api.set_configs({"template": "office"}),
    "import_theme": lambda api: api.import_theme({"source": "C:/themes/paper"}),
    "remove_theme": lambda api: api.remove_theme("paper"),
    "export_theme_template": lambda api: api.export_theme_template({"destination": "C:/out"}),
    "open_theme_location": lambda api: api.open_theme_location(),
    "convert": lambda api: api.convert({"inputs": [], "output_dir": "out"}),
    "prepare_conversion": lambda api: api.prepare_conversion({"inputs": []}),
}


@pytest.mark.parametrize("name", sorted(MUTATING_CALLS))
def test_every_mutating_handler_is_refused_after_the_terminal_flag(
    onefile_tree, monkeypatch, name
):
    """P11-3：确认之后不再允许任何写入 —— 包括会 mkdir 的 open_theme_location。"""
    from gui.services import conversion, dialogs, lifecycle, themes

    api, _window = bridge_with_window()
    touched: list[str] = []
    guarded_dependencies = (
        (lifecycle, "save_config"),
        (themes, "install_theme"),
        (themes, "uninstall_theme"),
        (themes, "export_template"),
        (themes, "ensure_theme_root"),
        (conversion, "build_conversion_plan"),
    )
    for module, attribute in guarded_dependencies:
        monkeypatch.setattr(
            module,
            attribute,
            lambda *args, _name=attribute, **kwargs: touched.append(_name),
        )
    monkeypatch.setattr(dialogs, "_pick_directory", lambda _title: touched.append("dialog") or "")

    api.request_user_data_removal()
    assert api.removal_requested() is True, name

    result = MUTATING_CALLS[name](api)

    assert touched == [], name + " reached core after the terminal flag"
    if isinstance(result, dict):
        refused = (
            result.get("ok") is False
            or result.get("success") is False
            or bool(result.get("errors"))
        )
        assert refused, result


def test_a_mutation_in_flight_refuses_the_removal_request(onefile_tree, monkeypatch):
    """P11-3 的原子部分：在途的写入不是「之后被禁」，而是根本不允许开始终止。"""
    from gui.services import themes

    api, window = bridge_with_window()
    started = threading.Event()
    release = threading.Event()

    def slow_import(_source, *, replace=False):
        started.set()
        release.wait(5)
        return "paper"

    monkeypatch.setattr(themes, "install_theme", slow_import)
    worker = threading.Thread(target=lambda: api.import_theme({"source": "C:/themes/paper"}))
    worker.start()
    assert started.wait(5), "fixture: the import is in flight"
    try:
        refused = api.request_user_data_removal()
        assert refused.get("ok") is False, refused
        assert refused.get("error"), refused
        assert api.removal_requested() is False, "a refused request must not set the terminal flag"
        assert window.destroyed == 0, "and it must not end the window"
    finally:
        release.set()
        worker.join(5)


def test_an_open_native_dialog_refuses_the_removal_request(onefile_tree, monkeypatch):
    """dialog 不是 storage mutation，但终止转换期间也不能强拆它。"""
    from gui.services import dialogs

    api, window = bridge_with_window()
    opened = threading.Event()
    release = threading.Event()

    def blocking_directory(_title):
        opened.set()
        release.wait(5)
        return ""

    monkeypatch.setattr(dialogs, "_pick_directory", blocking_directory)
    worker = threading.Thread(target=lambda: api.import_theme({}))
    worker.start()
    assert opened.wait(5), "fixture: the dialog is open"
    try:
        refused = api.request_user_data_removal()
        assert refused.get("ok") is False, refused
        assert api.removal_requested() is False
        assert window.destroyed == 0
    finally:
        release.set()
        worker.join(5)

    accepted = api.request_user_data_removal()

    assert accepted.get("ok") is not False, accepted
    assert api.removal_requested() is True, "once nothing is in flight the request goes through"


DIALOG_CALLS = {
    "select_input_files": lambda api: api.select_input_files(),
    "select_input_directory": lambda api: api.select_input_directory(),
    "select_output_directory": lambda api: api.select_output_directory(),
}


@pytest.mark.parametrize("name", sorted(DIALOG_CALLS))
def test_native_dialogs_are_refused_after_the_terminal_flag(onefile_tree, monkeypatch, name):
    """dialog 也过同一把 gate：只让 removal 去查 dialog 锁会留一个 check-then-act 的窗口。"""
    import tkinter
    import tkinter.filedialog

    api, _window = bridge_with_window()
    opened: list[str] = []

    class StubTk:
        def withdraw(self):
            return None

        def attributes(self, *_args):
            return None

        def destroy(self):
            return None

    monkeypatch.setattr(tkinter, "Tk", StubTk)
    monkeypatch.setattr(
        tkinter.filedialog, "askopenfilenames", lambda **_kwargs: opened.append("files") or ()
    )
    monkeypatch.setattr(
        tkinter.filedialog, "askdirectory", lambda **_kwargs: opened.append("dir") or "C:/picked"
    )

    api.request_user_data_removal()
    assert api.removal_requested() is True, name

    DIALOG_CALLS[name](api)

    assert opened == [], name + " reached tkinter after the terminal flag"


def test_an_accepted_request_closes_the_log_before_it_destroys_the_window(
    onefile_tree, monkeypatch
):
    """AGENTS §23：确认之后禁止日志写入 —— 所以 file handler 必须早于窗口销毁就关闭。"""
    import gui.api as gui_api
    from core import logger as core_logger
    from gui.services import lifecycle

    events: list[str] = []

    class OrderedWindow(WindowStub):
        def destroy(self) -> None:
            events.append("destroy")
            super().destroy()

    api = gui_api.BridgeApi()
    window = OrderedWindow()
    api.attach_window(window)
    original_close = getattr(core_logger, "close_file_logging", None)
    assert original_close is not None, "core.logger must offer close_file_logging()"

    def spy_close() -> str | None:
        events.append("close_log")
        return original_close()

    monkeypatch.setattr(lifecycle, "close_file_logging", spy_close)

    reply = api.request_user_data_removal()

    assert reply.get("ok") is not False, reply
    assert events == ["close_log", "destroy"], events
    assert window.destroyed == 1


# ── the application owns the order, and nothing recreates what was removed ───────────


def test_the_app_starts_visible_and_closes_logging_before_deleting_and_recreates_nothing(
    onefile_tree, monkeypatch
):
    """P11-10：应用可见启动；accepted → close_file_logging → destroy → start() 返回 → 删除 → 退出。

    这条契约同时是「删除不得发生在活着的 WebView2 里」的判据：真实删除必须发生在
    `webview.start()` 返回之后，而日志文件必须在删除前就已经关闭，之后也不能被重新创建。
    """
    import gui.app as gui_app
    from core import logger as core_logger

    module = user_data()
    events: list[str] = []

    class StubSubscription:
        def __iadd__(self, _handler):
            return self

    class StubWindow:
        def __init__(self):
            self.events = type("Events", (), {"loaded": StubSubscription()})()

        def evaluate_js(self, _script):
            return None

    created: list[Any] = []

    class StubApi:
        """Stands in for the bridge, including the log close an accepted request performs."""

        def __init__(self):
            self.requested = False
            created.append(self)

        def attach_window(self, window):
            self.window = window

        def request_user_data_removal(self):
            events.append("request")
            self.requested = True
            # The production bridge closes the file log while it accepts the request, through the
            # same patched function this stub resolves at call time.
            closer = getattr(core_logger, "close_file_logging", None)
            assert closer is not None, "core.logger must offer close_file_logging()"
            closer()
            return {"ok": True}

        def _should_remove_user_data_on_exit(self):
            return self.requested

    monkeypatch.setattr(gui_app, "BridgeApi", StubApi)
    monkeypatch.setattr(gui_app, "load_gui_document", lambda: "<html><body></body></html>")
    monkeypatch.setattr(gui_app, "close_splash", lambda: None)
    window_options: dict[str, Any] = {}

    def fake_create_window(*_args, **kwargs):
        window_options.update(kwargs)
        return StubWindow()

    monkeypatch.setattr(gui_app.webview, "create_window", fake_create_window)
    monkeypatch.setattr("core.renderer_node.validate_renderer_runtime", lambda: None)

    def fake_start(**_kwargs):
        events.append("start")
        created[-1].request_user_data_removal()

    monkeypatch.setattr(gui_app.webview, "start", fake_start)

    close_log = getattr(core_logger, "close_file_logging", None)
    assert close_log is not None, "core.logger must offer close_file_logging()"
    original_close = close_log
    original_remove = module.remove_user_data

    def spy_close():
        events.append("close_log")
        return original_close()

    def spy_remove():
        events.append("delete")
        return original_remove()

    monkeypatch.setattr(core_logger, "close_file_logging", spy_close)
    monkeypatch.setattr(module, "remove_user_data", spy_remove)

    log_path = paths.log_path()
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    try:
        gui_app.main()
    finally:
        for handler in root.handlers:
            if handler not in previous_handlers:
                handler.close()
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)

    assert events == ["start", "request", "close_log", "delete"], events
    assert window_options.get("hidden") is False
    assert not os.path.exists(log_path), "the log must not be recreated after the removal"
    assert not onefile_tree["profile"].exists()
    assert not onefile_tree["runtime"].exists()
    assert not onefile_tree["assets"].exists()
    assert not onefile_tree["legacy"].exists()
    assert onefile_tree["exe"].is_file(), "the executable survives"
