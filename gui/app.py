"""MarkdownReader GUI entry point — pywebview window with log bridging."""

import importlib
import json
import logging
import os
import sys
import threading
from typing import Protocol, cast

# Ensure project root is on sys.path so gui.api can import core.*
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import webview  # noqa: E402
from webview.dom import DOMEventHandler  # noqa: E402

from core.config import BUNDLE_ROOT  # noqa: E402
from gui.api import BridgeApi  # noqa: E402

_logger = logging.getLogger("gui")


class SplashModule(Protocol):
    """Runtime interface exposed by PyInstaller's splash module."""

    def close(self) -> None: ...


def load_pyi_splash() -> SplashModule | None:
    """Load PyInstaller's runtime-only splash module when it is available."""
    try:
        return cast(SplashModule, importlib.import_module("pyi_splash"))
    except ImportError:
        return None


_pyi_splash = load_pyi_splash()


class WebViewLogHandler(logging.Handler):
    """Buffer startup logs, then push records to the webview log panel."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setFormatter(logging.Formatter("%(message)s"))
        self._ready = False
        self._pending = []
        self._lock = threading.Lock()

    def emit(self, record):
        entry = (record.levelname, self.format(record))
        with self._lock:
            if not self._ready:
                self._pending.append(entry)
                return
        self._write(*entry)

    def mark_ready(self):
        """Flush records after appendLog is available in the loaded page."""
        with self._lock:
            self._ready = True
            pending = self._pending
            self._pending = []
        for entry in pending:
            self._write(*entry)

    def _write(self, level, message):
        try:
            level_json = json.dumps(level)
            message_json = json.dumps(message, ensure_ascii=False)
            self.window.evaluate_js(f"appendLog({level_json},{message_json})")
        except Exception:
            pass


def get_webview_storage_path() -> str:
    """Return a persistent per-user WebView2 cache directory."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "MarkdownReader", "WebView2")


def close_splash():
    """Close the PyInstaller splash screen when running from a frozen build."""
    if _pyi_splash is None:
        return
    try:
        _pyi_splash.close()
    except Exception:
        _logger.debug("启动图已关闭。", exc_info=True)


def load_gui_document() -> str:
    """Load and inline GUI assets so WebView2 cannot reuse stale file URLs."""
    assets_dir = os.path.join(BUNDLE_ROOT, "gui", "assets")
    html_path = os.path.join(assets_dir, "index.html")
    css_path = os.path.join(assets_dir, "gui.css")
    js_path = os.path.join(assets_dir, "gui.js")
    required = (html_path, css_path, js_path)
    if not all(os.path.isfile(path) for path in required):
        return "<html><body><h1>MarkdownReader</h1><p>HTML asset not found.</p></body></html>"

    with open(html_path, "r", encoding="utf-8") as handle:
        document = handle.read()
    with open(css_path, "r", encoding="utf-8") as handle:
        css = handle.read()
    with open(js_path, "r", encoding="utf-8") as handle:
        javascript = handle.read()

    document = document.replace(
        '<link rel="stylesheet" href="gui.css">',
        f"<style>\n{css}\n</style>",
        1,
    )
    document = document.replace(
        '<script src="gui.js"></script>',
        f"<script>\n{javascript}\n</script>",
        1,
    )
    return document


def main():
    # Setup root logger
    from core.logger import setup_logging

    setup_logging(verbose=True)

    # Create the API instance
    api = BridgeApi()

    # Inline the current HTML/CSS/JS sources. Loading a fixed file:// URL with a
    # persistent WebView2 profile can otherwise display stale cached assets.
    html_content = load_gui_document()

    # Create window
    kwargs = {
        "js_api": api,
        "width": 720,
        "height": 620,
        # The two-column desktop layout remains usable down to the default
        # width.  A narrower native window clips the workspace navigation, so
        # keep the window constraint aligned with the actual layout contract.
        "min_size": (720, 500),
        "resizable": True,
        "easy_drag": False,
        "background_color": "#ffffff",
        "hidden": True,
    }
    kwargs["html"] = html_content
    window = webview.create_window("MarkdownReader — Markdown to HTML", **kwargs)
    if window is None:
        raise RuntimeError("无法创建 MarkdownReader 窗口。")
    api.attach_window(window)

    # Attach log bridge
    handler = WebViewLogHandler(window)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.DEBUG)

    def _drop_paths(event) -> list[str]:
        transfer = event.get("dataTransfer") or event.get("domTransfer") or {}
        paths: list[str] = []
        for item in transfer.get("files", []):
            if isinstance(item, dict):
                path = item.get("pywebviewFullPath") or item.get("path")
            else:
                path = str(item)
            if path:
                paths.append(path)
        return paths

    def _set_drop_overlay(active: bool):
        try:
            window.evaluate_js(f"setDropOverlay({str(active).lower()})")
        except Exception:
            pass

    def on_drop(event):
        paths = _drop_paths(event)
        _set_drop_overlay(False)
        if not paths:
            return
        paths_json = json.dumps(paths, ensure_ascii=False)
        window.evaluate_js(f"acceptDroppedInputs({paths_json})")

    def bind_drop_events():
        document = window.dom.document
        document.events.dragenter += DOMEventHandler(
            lambda _event: _set_drop_overlay(True),
            prevent_default=True,
            stop_propagation=True,
        )
        document.events.dragover += DOMEventHandler(
            lambda _event: _set_drop_overlay(True),
            prevent_default=True,
            stop_propagation=True,
            debounce=250,
        )
        document.events.drop += DOMEventHandler(
            on_drop,
            prevent_default=True,
            stop_propagation=True,
        )

    def reveal_window():
        close_splash()
        bind_drop_events()
        window.show()
        handler.mark_ready()

    window.events.loaded += reveal_window

    _logger.info("MarkdownReader 已启动，请选择 Markdown 文件后开始转换。")

    try:
        webview.start(
            gui="edgechromium",
            private_mode=False,
            storage_path=get_webview_storage_path(),
        )
    finally:
        close_splash()


if __name__ == "__main__":
    main()
