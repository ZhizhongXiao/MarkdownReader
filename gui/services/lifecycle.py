"""GUI profile, storage, system-opening, and terminal-session lifecycle service."""

import json
import logging
import os
import sys
import threading
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from core import paths, user_data
from core import version as core_version
from core.config import PRODUCTION_RENDERER_VERSION, load_config, save_config
from core.external_themes import theme_root
from core.logger import close_file_logging

_logger = logging.getLogger("gui")

RUNTIME_NOTE = (
    "日志与 WebView2 profile 都在 runtime 内（三种布局都在用户数据目录下）；"
    "「移除 MarkdownReader 用户数据」仅 onefile 提供：确认后立即停止日志写入，"
    "窗口关闭后再删除 profile / assets / runtime 与遗留的旧配置。"
)

REMOVAL_REFUSAL = "移除用户数据已开始，本次操作被拒绝。"


class WebViewWindow(Protocol):
    """The minimal pywebview window surface owned by this service."""

    def evaluate_js(self, script: str, /) -> object: ...

    def destroy(self) -> None: ...


def _storage_mode() -> str:
    """Return source / onedir / onefile, as core.paths resolves the current process."""
    if not paths.is_frozen():
        return "source"
    return "onedir" if paths.is_onedir() else "onefile"


def _normalize_config_path(path: str) -> str:
    """Return a stable JSON path with forward slashes."""
    return os.path.normpath(path).replace("\\", "/") if path else ""


def _normalize_input_root(path: str) -> str:
    """Persist file inputs as their parent directory, and directory inputs as-is."""
    raw = str(path or "").strip().strip('"')
    if not raw:
        return ""

    normalized = os.path.normpath(raw)
    if os.path.isdir(normalized):
        return _normalize_config_path(normalized)

    _, ext = os.path.splitext(normalized)
    if os.path.isfile(normalized) or ext.lower() in {".md", ".markdown"}:
        parent = os.path.dirname(normalized)
        return _normalize_config_path(parent or normalized)

    return _normalize_config_path(normalized)


def _file_uri(path: str) -> str:
    """Return a file URI so the system opens a local document as one."""
    return Path(path).resolve().as_uri()


class LifecycleStorageService:
    """Own shared operation gating, storage facts, system opening, and terminal removal."""

    def __init__(self) -> None:
        self._window: WebViewWindow | None = None
        self._state_lock = threading.Lock()
        self._operations_in_flight = 0
        self._removal_requested = False

    @contextmanager
    def operation(self) -> Iterator[bool]:
        """Admit one bridge operation unless terminal removal was accepted."""
        with self._state_lock:
            if self._removal_requested:
                yield False
                return
            self._operations_in_flight += 1
        try:
            yield True
        finally:
            with self._state_lock:
                self._operations_in_flight -= 1

    def attach_window(self, window: WebViewWindow) -> None:
        self._window = window

    def notify_conversion_status(
        self,
        source_path: str,
        status: str,
        warnings: list[str] | None = None,
        output_path: str = "",
    ) -> None:
        if self._window is None:
            return
        try:
            args = json.dumps(
                [source_path, status, warnings or [], output_path],
                ensure_ascii=False,
            )
            self._window.evaluate_js(f"updateConversionStatus(...{args})")
        except Exception:
            _logger.debug("推送转换状态失败。", exc_info=True)

    def get_config(self) -> dict:
        """Return the full merged configuration."""
        return load_config()

    def set_configs(self, overrides: dict) -> None:
        """Normalize GUI paths, then persist configuration through the core writer."""
        cfg = load_config()
        cfg.update(overrides)
        if "input" in cfg:
            cfg["input"] = _normalize_input_root(cfg["input"])
        if "output" in cfg:
            cfg["output"] = _normalize_config_path(str(cfg["output"]))
        save_config(cfg)

    def get_storage_info(self) -> dict:
        """Return the real locations used by this build."""
        return {
            "mode": _storage_mode(),
            "user_data_root": paths.user_data_root(),
            "config_path": paths.config_path(),
            "external_themes_root": theme_root(),
            "runtime_root": paths.runtime_root(),
            "runtime_note": RUNTIME_NOTE,
            "removal_available": user_data.removal_available(),
            "removal_items": user_data.removal_items(),
        }

    def get_about_info(self) -> dict:
        """Return the facts the About panel is allowed to state."""
        return {
            "name": "MarkdownReader",
            "version": core_version.__version__,
            "renderer_version": PRODUCTION_RENDERER_VERSION,
            "python": sys.version.split()[0],
            "mode": _storage_mode(),
        }

    def open_file_uri(self, path: str) -> None:
        """Open a path as a file URI, used after the converter has produced its output."""
        webbrowser.open(_file_uri(path))

    def open_file(self, path: str) -> None:
        """Open an existing file with the system's default application."""
        if os.path.isfile(path):
            self.open_file_uri(path)

    def open_directory(self, path: str) -> None:
        """Open an existing directory in the platform's file explorer."""
        if os.path.isdir(path):
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')

    def request_user_data_removal(self) -> dict:
        """End the session; actual filesystem deletion happens after the GUI loop returns."""
        if not user_data.removal_available():
            return {"ok": False, "error": "只有 onefile 构建提供「移除 MarkdownReader 用户数据」。"}
        with self._state_lock:
            if self._removal_requested:
                return {"ok": False, "error": "移除用户数据的请求已经发出。"}
            if self._operations_in_flight:
                return {"ok": False, "error": "仍有操作在执行，请稍后再试。"}
            self._removal_requested = True
        close_file_logging()
        if not self._destroy_window():
            with self._state_lock:
                self._removal_requested = False
            return {"ok": False, "error": "无法关闭窗口，用户数据未删除。"}
        return {"ok": True, "error": ""}

    def _destroy_window(self) -> bool:
        """Return False when no window exists or destroying it fails."""
        if self._window is None:
            return False
        try:
            self._window.destroy()
        except Exception:
            _logger.warning("销毁窗口失败，本次移除请求被拒绝。", exc_info=True)
            return False
        return True

    def should_remove_user_data_on_exit(self) -> bool:
        """Expose the app-loop seam for a previously accepted terminal removal request."""
        with self._state_lock:
            return self._removal_requested
