"""Phase 10: the log and the WebView2 profile are runtime data, and `core.paths` owns them.

Phase 9B's ownership reconnaissance found both outside the frozen classification:

* the log went to `application_dir()`, which for onefile means "beside the EXE -- wherever the
  user put it", and for onedir means a file inside an otherwise self-contained folder;
* the WebView2 profile was always `%LOCALAPPDATA%/MarkdownReader/WebView2`, which broke onedir's
  promise that deleting the application folder is a complete removal.

These contracts look at the two facts where they are observable: the real log file a real
`setup_logging()` opens, and the path the GUI hands to `webview.start()`.
"""

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import paths  # noqa: E402

LOGGER_SOURCE = ROOT / "core" / "logger.py"
GUI_APP_SOURCE = ROOT / "gui" / "app.py"


def test_setup_logging_writes_inside_runtime_root(monkeypatch, tmp_path):
    """真实调用一次 `setup_logging()`，检查它打开的文件 handler 落在哪里。

    The root logger is snapshotted and restored, and the handler is closed, because
    `setup_logging()` reconfigures global logging state with `force=True` and Windows keeps the
    file locked until its handler is closed. `logging.shutdown()` is deliberately not called:
    it would close pytest's own capture handlers for the rest of the session.

    `source_root` is pointed at the temporary tree first, so even the red phase -- where the
    logger still asks `application_dir()` -- cannot write `MarkdownReader.log` into the
    repository it is complaining about.
    """
    from core.logger import setup_logging

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(paths, "source_root", lambda: str(tmp_path))

    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    opened: list[logging.FileHandler] = []
    try:
        setup_logging(verbose=True)

        opened = [handler for handler in root.handlers if isinstance(handler, logging.FileHandler)]
        assert opened, "setup_logging() must still write a log file"
        target = os.path.abspath(opened[0].baseFilename)
        assert os.path.dirname(target) == os.path.abspath(paths.runtime_root()), target
        assert os.path.isfile(target), target
        assert not (tmp_path / "MarkdownReader.log").exists(), (
            "the log must not be written next to the application directory"
        )
    finally:
        for handler in opened:
            handler.close()
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)


def test_the_logger_asks_the_paths_module_where_the_log_goes():
    """logger 只负责「建目录 + 装 handler」，位置是 `core.paths` 的事实。"""
    source = LOGGER_SOURCE.read_text(encoding="utf-8")

    assert "paths.log_path()" in source
    assert "get_application_dir" not in source
    assert '"MarkdownReader.log"' not in source, "the file name belongs to core/paths.py"


def test_the_webview_profile_comes_from_the_path_resolver():
    """GUI 不再自行读取 %LOCALAPPDATA% 来决定 WebView2 位置。"""
    source = GUI_APP_SOURCE.read_text(encoding="utf-8")

    assert "storage_path=paths.webview_storage_root()" in source
    assert "get_webview_storage_path" not in source
    assert "LOCALAPPDATA" not in source


def test_the_webview_profile_is_a_runtime_subdirectory():
    """它是 runtime 数据的一个子目录，而不是一个独立的用户级位置。"""
    resolved = paths.webview_storage_root()

    assert resolved.endswith(os.sep + "WebView2"), resolved
    assert resolved != paths.runtime_root()
