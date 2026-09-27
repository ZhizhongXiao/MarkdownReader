"""Phase 7A: one module knows where MarkdownReader reads and writes.

AGENTS section 24 asks for the source / onedir / onefile / bundle / profile / assets /
runtime decisions to live in a small path module -- external themes (Phase 7) need a
writable, persistent home, and no business module should have to ask PyInstaller
questions. These cases pin the three layouts and the single-source rule.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config as core_config  # noqa: E402
from core import paths  # noqa: E402


@pytest.fixture(autouse=True)
def source_mode(monkeypatch):
    """Every case starts from "running from source" and opts into a frozen mode."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)


def freeze(monkeypatch, exe_dir: Path, bundle: Path) -> None:
    """Put the process into a frozen build whose bundle lives at ``bundle``."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "MarkdownReader.exe"), raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)


def test_source_mode_keeps_user_data_inside_the_repository(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "source_root", lambda: str(tmp_path))

    assert paths.is_frozen() is False
    assert paths.user_data_root() == str(tmp_path / ".runtime")
    assert paths.profile_root() == str(tmp_path / ".runtime" / "profile")
    assert paths.assets_root() == str(tmp_path / ".runtime" / "assets")
    assert paths.runtime_root() == str(tmp_path / ".runtime" / "runtime")
    assert paths.external_themes_root() == str(
        tmp_path / ".runtime" / "assets" / "themes" / "external"
    )
    assert paths.config_path() == str(tmp_path / ".runtime" / "profile" / "config.json")


def test_onedir_keeps_data_next_to_the_executable(monkeypatch, tmp_path):
    app = tmp_path / "MarkdownReader"
    internal = app / "_internal"
    internal.mkdir(parents=True)
    freeze(monkeypatch, app, internal)

    assert paths.is_frozen() is True
    assert paths.application_dir() == str(app)
    assert paths.bundle_root() == str(internal)
    assert paths.user_data_root() == str(app / "data")
    assert paths.external_themes_root() == str(app / "data" / "assets" / "themes" / "external")


def test_onefile_uses_local_app_data(monkeypatch, tmp_path):
    extraction = tmp_path / "_MEI12345"
    extraction.mkdir()
    install = tmp_path / "install"
    install.mkdir()
    freeze(monkeypatch, install, extraction)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    assert paths.user_data_root() == str(tmp_path / "LocalAppData" / "MarkdownReader")
    assert paths.config_path() == str(
        tmp_path / "LocalAppData" / "MarkdownReader" / "profile" / "config.json"
    )


def test_onefile_still_works_without_local_app_data(monkeypatch, tmp_path):
    """%LOCALAPPDATA% 缺失时不得抛错：回落到用户主目录下的 AppData/Local。"""
    extraction = tmp_path / "_MEI99"
    extraction.mkdir()
    install = tmp_path / "install"
    install.mkdir()
    freeze(monkeypatch, install, extraction)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("APPDATA", "")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    root = paths.user_data_root()
    assert root.endswith("MarkdownReader")
    assert os.path.isabs(root)
    assert str(tmp_path) in root


def test_resolving_paths_creates_nothing(monkeypatch, tmp_path):
    """7A 是纯路径层：查路径不得产生目录（创建属于导入/转换时刻）。"""
    monkeypatch.setattr(paths, "source_root", lambda: str(tmp_path))

    for resolve in (
        paths.user_data_root,
        paths.profile_root,
        paths.assets_root,
        paths.runtime_root,
        paths.external_themes_root,
        paths.config_path,
        paths.log_path,
        paths.webview_storage_root,
    ):
        assert resolve()
    assert list(tmp_path.iterdir()) == []


def test_paths_with_spaces_and_cjk_survive(monkeypatch, tmp_path):
    """项目可能被放在含空格或中文的目录下：路径必须原样保留、可再次交给文件系统。"""
    root = tmp_path / "含空格 与中文" / "MarkdownReader 源码"
    root.mkdir(parents=True)
    monkeypatch.setattr(paths, "source_root", lambda: str(root))

    resolved = paths.external_themes_root()
    assert resolved.startswith(str(root))
    assert ".runtime" in resolved
    assert os.path.isdir(str(root))


def test_only_the_paths_module_judges_the_frozen_layout():
    """AGENTS section 24：core/gui/tools 里除 core/paths.py 外不得判断 frozen/_MEIPASS。"""
    offenders = []
    for base in ("core", "gui", "tools"):
        for path in sorted((ROOT / base).rglob("*.py")):
            if path == ROOT / "core" / "paths.py":
                continue
            text = path.read_text(encoding="utf-8")
            offenders.extend(
                path.as_posix() + " :: " + token
                for token in ("sys.frozen", "_MEIPASS")
                if token in text
            )
    assert offenders == [], offenders


def test_the_config_module_still_exposes_the_paths_it_always_did():
    """既有调用方（index_builder / renderer_node / viewer_assets / gui）不受影响。"""
    assert paths.bundle_root() == core_config.BUNDLE_ROOT
    assert paths.application_dir() == core_config.PROJECT_ROOT

def under(child: str, parent: str) -> bool:
    """Return True when ``child`` resolves inside ``parent``, separators and case aside."""
    child_norm = os.path.normcase(os.path.normpath(os.path.abspath(child)))
    parent_norm = os.path.normcase(os.path.normpath(os.path.abspath(parent)))
    return os.path.commonpath([child_norm, parent_norm]) == parent_norm


# Every path MarkdownReader may write to. This tuple is the definition of "owned storage": a
# resolver that forgets a segment, or that leaks outside the layout, has to fail here. The
# names are looked up per case, so a resolver that does not exist yet fails its own case
# instead of breaking collection for the whole file.
OWNED_WRITABLE_PATHS = (
    "profile_root",
    "assets_root",
    "runtime_root",
    "external_themes_root",
    "config_path",
    "log_path",
    "webview_storage_root",
)


def test_the_log_and_the_webview_profile_live_under_runtime_root(monkeypatch, tmp_path):
    """Phase 10：log 与 WebView2 profile 都是 runtime 数据，三种布局下都必须落在 runtime_root 里。

    Phase 9B 的 ownership 侦察发现两者都不在这儿：log 落在 `application_dir()`（onefile 下就是
    「EXE 旁边 —— 用户把它放哪儿就是哪儿」），WebView2 恒在 `%LOCALAPPDATA%`（这破坏了 onedir
    的「删掉整个目录即完整移除」）。
    """
    monkeypatch.setattr(paths, "source_root", lambda: str(tmp_path))
    assert under(paths.log_path(), paths.runtime_root())
    assert under(paths.webview_storage_root(), paths.runtime_root())
    assert os.path.basename(paths.log_path()) == "MarkdownReader.log"
    assert os.path.basename(paths.webview_storage_root()) == "WebView2"

    app = tmp_path / "MarkdownReader"
    (app / "_internal").mkdir(parents=True)
    freeze(monkeypatch, app, app / "_internal")
    assert under(paths.log_path(), paths.runtime_root())
    assert under(paths.webview_storage_root(), paths.runtime_root())

    extraction = tmp_path / "_MEI4242"
    extraction.mkdir()
    install = tmp_path / "install"
    install.mkdir()
    freeze(monkeypatch, install, extraction)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    assert under(paths.log_path(), paths.runtime_root())
    assert under(paths.webview_storage_root(), paths.runtime_root())
    assert under(paths.log_path(), tmp_path / "LocalAppData" / "MarkdownReader")
    assert under(paths.webview_storage_root(), tmp_path / "LocalAppData" / "MarkdownReader")


@pytest.mark.parametrize("name", OWNED_WRITABLE_PATHS)
def test_onedir_keeps_every_owned_path_inside_its_own_directory(monkeypatch, tmp_path, name):
    """onedir 的「删掉整个目录即完整移除」只有在全部自有可写路径都在它下面时才成立。"""
    app = tmp_path / "MarkdownReader"
    (app / "_internal").mkdir(parents=True)
    freeze(monkeypatch, app, app / "_internal")

    resolved = getattr(paths, name)()

    assert under(resolved, app / "data"), name + " must stay inside the application data directory"


@pytest.mark.parametrize("name", OWNED_WRITABLE_PATHS)
def test_onefile_keeps_every_owned_path_inside_local_app_data(monkeypatch, tmp_path, name):
    """onefile 是只读的单文件 EXE：全部自有可写路径都必须落在 %LOCALAPPDATA%/MarkdownReader。"""
    extraction = tmp_path / "_MEI4243"
    extraction.mkdir()
    install = tmp_path / "install"
    install.mkdir()
    freeze(monkeypatch, install, extraction)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    resolved = getattr(paths, name)()

    assert under(resolved, tmp_path / "LocalAppData" / "MarkdownReader"), (
        name + " must stay inside the onefile user data root"
    )


def test_only_the_paths_module_decides_the_user_storage_locations():
    """AGENTS §24 的姊妹规则：%LOCALAPPDATA% 的推导只属于 core/paths.py。

    这是布局事实（onedir 在应用目录下、onefile 在用户目录下）。别的模块自己拼一次，两处就会
    漂移，而 onedir 的删除承诺正是建立在这条单一来源之上。
    """
    offenders = []
    for base in ("core", "gui", "tools"):
        for path in sorted((ROOT / base).rglob("*.py")):
            if path == ROOT / "core" / "paths.py":
                continue
            text = path.read_text(encoding="utf-8")
            offenders.extend(
                path.as_posix() + " :: " + token
                for token in ("LOCALAPPDATA", "APPDATA")
                if token in text
            )
    assert offenders == [], offenders

    assert core_config.get_bundle_root() == paths.bundle_root()
    assert core_config.get_application_dir() == paths.application_dir()
