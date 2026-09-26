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
            for token in ("sys.frozen", "_MEIPASS"):
                if token in text:
                    offenders.append(path.as_posix() + " :: " + token)
    assert offenders == [], offenders


def test_the_config_module_still_exposes_the_paths_it_always_did():
    """既有调用方（index_builder / renderer_node / viewer_assets / gui）不受影响。"""
    assert core_config.BUNDLE_ROOT == paths.bundle_root()
    assert core_config.PROJECT_ROOT == paths.application_dir()
    assert core_config.get_bundle_root() == paths.bundle_root()
    assert core_config.get_application_dir() == paths.application_dir()
