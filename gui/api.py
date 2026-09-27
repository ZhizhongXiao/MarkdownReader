"""Bridge API exposed to the GUI's JavaScript context.

All methods are callable from JS via `pywebview.api.xxx()`.
This layer is thin — it only marshals data and delegates to core.
"""

import json
import logging
import os
import sys
import threading
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from core import paths
from core import version as core_version
from core.config import PRODUCTION_RENDERER_VERSION, load_config, save_config
from core.conversion_plan import build_conversion_plan, document_output_map
from core.external_themes import (
    ensure_theme_root,
    export_template,
    theme_inventory,
    theme_root,
    theme_state,
)
from core.external_themes import import_theme as install_theme
from core.external_themes import remove_theme as uninstall_theme
from core.viewer_assets import builtin_theme_ids, normalize_theme_id

_logger = logging.getLogger("gui")

# The exported template lands in a fixed child folder of the picked directory: the core
# exporter refuses an existing target, so a stable name turns "already exported" into a
# message the user can read instead of an overwrite or a silent no-op.
EXPORTED_TEMPLATE_DIR_NAME = "markdownreader-theme-template"

# `runtime_root()` has no production writer yet (logs and the WebView2 profile move there
# in Phase 10). Until that ownership is closed, the storage section must not imply that a
# "remove user data" action would cover them.
RUNTIME_NOTE = (
    "预留：日志与 WebView2 尚未迁入 runtime（Phase 10）。在整份 ownership 收口之前，"
    "设置页不提供「移除用户数据」。"
)


def _pick_directory(title: str) -> str:
    """Open a folder dialog and return the picked path, or "" when it was cancelled."""
    from tkinter import Tk
    from tkinter.filedialog import askdirectory

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = askdirectory(title=title)
    root.destroy()
    return path if path else ""


def _storage_mode() -> str:
    """Return source / onedir / onefile, as `core.paths` answers it."""
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
    """Return a file:// URI, so the system opens a local document as one.

    A bare Windows path is handed to the .html association instead, and a stale
    association can then open something else, or nothing at all.
    """
    return Path(path).resolve().as_uri()


class BridgeApi:
    """Public API exposed to pywebview's JavaScript context."""

    def __init__(self) -> None:
        self._window = None
        # pywebview runs every JS call in a thread of its own, and tkinter keeps a
        # single process-wide default root. A second dialog opened while the first
        # one still owns that root calls Tcl from the wrong thread and dies with
        # "main thread is not in main loop". An overlap is therefore refused
        # rather than queued: the caller gets an empty answer, like a cancel.
        self._dialog_lock = threading.Lock()

    @contextmanager
    def _one_dialog_at_a_time(self) -> Iterator[bool]:
        """Yield True when this call may open a native dialog, False when not."""
        if not self._dialog_lock.acquire(blocking=False):
            yield False
            return
        try:
            yield True
        finally:
            self._dialog_lock.release()

    def attach_window(self, window) -> None:
        """Attach the created webview window for conversion progress events."""
        self._window = window

    def _notify_conversion_status(
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

    # ── File selection ──────────────────────────────────────

    def select_input_files(self) -> list[str]:
        """Open a native file dialog that supports selecting multiple files."""
        from tkinter import Tk
        from tkinter.filedialog import askopenfilenames

        with self._one_dialog_at_a_time() as opened:
            if not opened:
                return []
            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            paths = askopenfilenames(
                title="选择一个或多个 Markdown 文件",
                filetypes=[("Markdown", "*.md *.markdown"), ("All Files", "*.*")],
            )
            root.destroy()
            return list(paths) if paths else []

    def select_input_directory(self) -> str:
        """Open a folder dialog to select a directory of .md files."""
        from tkinter import Tk
        from tkinter.filedialog import askdirectory

        with self._one_dialog_at_a_time() as opened:
            if not opened:
                return ""
            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = askdirectory(title="选择包含 Markdown 文件的目录")
            root.destroy()
            return path if path else ""

    def select_output_directory(self) -> str:
        """Open a folder dialog for output directory."""
        from tkinter import Tk
        from tkinter.filedialog import askdirectory

        with self._one_dialog_at_a_time() as opened:
            if not opened:
                return ""
            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = askdirectory(title="选择输出目录")
            root.destroy()
            return path if path else ""

    def prepare_conversion(self, request: dict | None = None) -> dict:
        """Expand inputs and return a read-only conversion plan for the GUI.

        The GUI sends one structured request, so ``inputs`` is a real list here
        rather than a JSON string: the bridge has a single protocol.
        """
        request = request or {}
        try:
            paths = request.get("inputs", [])
            if not isinstance(paths, list):
                raise ValueError("输入路径必须是数组。")
            output_dir = request.get("output_dir", "")
            preserve_structure = bool(request.get("preserve_structure", False))
            if not output_dir:
                output_dir = load_config().get("output", "output")
            return build_conversion_plan(paths, output_dir, preserve_structure)
        except Exception as exc:
            _logger.exception("生成转换预检清单失败")
            return {
                "inputs": [],
                "items": [],
                "source_root": "",
                "output_dir": request.get("output_dir", "") or "output",
                "warnings": [],
                "errors": [str(exc)],
                "counts": {"selected": 0, "directory": 0, "dependency": 0, "total": 0},
            }

    # ── Template ────────────────────────────────────────────

    def get_templates(self) -> list[str]:
        """Return the builtin themes a document's default theme may be chosen from.

        Builtin only on purpose: user themes are installed and selected on their own
        surface (Phase 9), while this list feeds the existing dropdown.
        """
        return builtin_theme_ids() or ["modern"]

    # ── Config ──────────────────────────────────────────────

    def get_config(self) -> dict:
        """Return full merged configuration."""
        return load_config()

    def set_configs(self, overrides: dict) -> None:
        """Update multiple config keys and persist them through the core writer.

        Only the GUI's own job is done here -- input and output are paths the user picked
        in this window, so they are normalized first. Everything else (the sectioned
        shape, the theme fields, the atomic write) belongs to `core.config`, so the GUI,
        the tests and any future CLI cannot drift apart.
        """
        cfg = load_config()
        cfg.update(overrides)
        if "input" in cfg:
            cfg["input"] = _normalize_input_root(cfg["input"])
        if "output" in cfg:
            cfg["output"] = _normalize_config_path(str(cfg["output"]))
        save_config(cfg)

    def get_theme_state(self) -> dict:
        """Return the remembered, selectable, missing and unusable user themes.

        `configured` is what config.json remembers -- a persistent fact -- while
        `selected` is the subset that is installed and valid right now, `missing` is the
        part that is not installed, and `invalid` is the part that is installed but no
        longer usable. Phase 9 needs all four: saving an unrelated setting with only
        `selected` in hand would erase a theme the user merely uninstalled for a moment,
        and "temporarily gone" and "present but broken" deserve different UI states.

        The classification belongs to `core.external_themes.theme_state()`, which shares
        its rules with the conversion path; this bridge only merges it with what the
        configuration remembers.
        """
        cfg = load_config()
        configured = list(cfg.get("external_themes") or [])
        default = str(cfg.get("template") or "")
        state = theme_state(configured, default=default)
        return {
            "default": default,
            "installed": state["installed"],
            "configured": configured,
            "selected": state["selected"],
            "missing": state["missing"],
            "invalid": state["invalid"],
            "warnings": state["warnings"],
        }

    # ── External theme management (settings page) ────────────

    def get_theme_inventory(self) -> dict:
        """Return every installed user theme with its own validity verdict.

        The settings page asks a different question than the main page: not "which theme
        does this document carry", but "what is installed here, and does it still work".
        That answer is a core rule (`core.external_themes.theme_inventory()`): the bridge
        marshals it, it does not read the theme registry itself (Phase 8C).
        """
        return theme_inventory()

    def import_theme(self, request: dict | None = None) -> dict:
        """Install a user theme, asking for its folder when the request carries none.

        The bridge owns the dialog so the page never has to know what a valid source looks
        like: `core.external_themes.import_theme()` validates before it copies anything, so
        a refused folder leaves no half-installed theme behind.
        """
        request = request or {}
        source = str(request.get("source") or "")
        if not source:
            with self._one_dialog_at_a_time() as opened:
                if not opened:
                    return {"ok": False, "id": "", "error": "已有对话框打开，请稍后再试。"}
                source = _pick_directory("选择要导入的主题目录")
            if not source:
                return {"ok": False, "id": "", "error": "未选择任何目录。"}
        try:
            theme_id = install_theme(source, replace=bool(request.get("replace", False)))
        except Exception as error:
            _logger.warning("导入外置主题失败：%s", error)
            return {"ok": False, "id": "", "error": str(error)}
        return {"ok": True, "id": theme_id, "error": ""}

    def remove_theme(self, theme_id: str) -> dict:
        """Delete an installed user theme. Packaged themes are never touched.

        Only the installed copy goes away: the configuration keeps remembering the id, so
        the main page reports it as `missing` afterwards. Uninstalling a theme is not the
        same act as unchecking it (AGENTS section 17).
        """
        try:
            uninstall_theme(theme_id)
        except Exception as error:
            _logger.warning("卸载外置主题失败：%s", error)
            return {"ok": False, "id": str(theme_id), "error": str(error)}
        return {"ok": True, "id": str(theme_id), "error": ""}

    def export_theme_template(self, request: dict | None = None) -> dict:
        """Copy the packaged theme template into a folder the user picks."""
        request = request or {}
        destination = str(request.get("destination") or "")
        if not destination:
            with self._one_dialog_at_a_time() as opened:
                if not opened:
                    return {"ok": False, "path": "", "error": "已有对话框打开，请稍后再试。"}
                picked = _pick_directory("选择导出主题模板的位置")
            if not picked:
                return {"ok": False, "path": "", "error": "未选择任何目录。"}
            destination = os.path.join(picked, EXPORTED_TEMPLATE_DIR_NAME)
        try:
            path = export_template(destination)
        except Exception as error:
            _logger.warning("导出主题模板失败：%s", error)
            return {"ok": False, "path": "", "error": str(error)}
        return {"ok": True, "path": path, "error": ""}

    def open_theme_location(self) -> dict:
        """Create the external theme directory if it is missing, then reveal it."""
        try:
            root = ensure_theme_root()
        except Exception as error:
            _logger.warning("创建外置主题目录失败：%s", error)
            return {"ok": False, "path": "", "error": str(error)}
        self.open_directory(root)
        return {"ok": True, "path": root, "error": ""}

    def get_storage_info(self) -> dict:
        """Return where this build keeps its data, exactly as `core.paths` resolves it."""
        return {
            "mode": _storage_mode(),
            "user_data_root": paths.user_data_root(),
            "config_path": paths.config_path(),
            "external_themes_root": theme_root(),
            "runtime_root": paths.runtime_root(),
            "runtime_note": RUNTIME_NOTE,
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

    # ── Conversion ──────────────────────────────────────────

    def convert(self, request: dict | None = None) -> dict:
        """Run conversion and return a result dict for one structured request.

        Args:
            request: mapping with inputs (a list of file or directory paths),
                output_dir, template, overwrite, build_index, auto_open and
                preserve_structure.

        Returns:
            {"success": bool, "files": [...], "errors": [...]}
        """
        try:
            from core.converter import process_batch, process_single
            from core.index_builder import make_index_filename
        except Exception as e:
            return {"success": False, "files": [], "errors": [str(e)]}

        request = request or {}
        paths = request.get("inputs", [])
        output_dir = request.get("output_dir", "")
        template = request.get("template", "modern")
        overwrite = bool(request.get("overwrite", False))
        build_index = bool(request.get("build_index", True))
        auto_open = bool(request.get("auto_open", False))
        preserve_structure = bool(request.get("preserve_structure", False))

        if not output_dir:
            output_dir = load_config().get("output", "output")

        # Build runtime overrides
        overrides = {
            "template": normalize_theme_id(template),
            "output": output_dir,
            "overwrite": overwrite,
            "build_index": build_index,
            "preserve_structure": preserve_structure,
        }

        try:
            cfg = load_config(runtime_overrides=overrides)
            plan = build_conversion_plan(paths, output_dir, preserve_structure)
            if plan.get("errors"):
                return {
                    "success": False,
                    "files": [],
                    "errors": plan["errors"],
                    "warnings": plan.get("warnings", []),
                    "documents": plan.get("items", []),
                    "output_dir": plan.get("output_dir", output_dir),
                    "entry_file": "",
                }

            items = plan.get("items", [])
            inputs = [item["source_path"] for item in items]
            if not items:
                return {"success": False, "files": [], "errors": ["未找到 Markdown 文件。"]}

            is_batch = len(inputs) > 1 or os.path.isdir(paths[0])
            actual_output_dir = plan["output_dir"]
            entry_file = ""
            documents: list[dict] = []
            warnings_list = list(plan.get("warnings", []))

            if is_batch:
                source_name = ""
                if len(paths) == 1 and os.path.isdir(paths[0]):
                    selected_root = os.path.abspath(paths[0])
                    source_name = os.path.basename(os.path.normpath(selected_root))

                index_filename = make_index_filename(source_name)
                results = process_batch(
                    inputs,
                    actual_output_dir,
                    cfg,
                    source_root=plan.get("source_root") or None,
                    index_filename=index_filename,
                    collection_name=source_name,
                    plan=plan,
                    progress_callback=self._notify_conversion_status,
                )
                files = [r.get("path", "") for r in results]
                documents = results
                for result in results:
                    warnings_list.extend(result.get("warnings", []))
                index_path = os.path.join(actual_output_dir, index_filename)
                if build_index and os.path.isfile(index_path):
                    entry_file = os.path.abspath(index_path)
                elif files:
                    entry_file = os.path.abspath(files[0])
                errors_list = [] if len(results) == len(items) else [
                    f"有 {len(items) - len(results)} 个文档生成失败。"
                ]
            else:
                item = items[0]
                out_path = item["output_path"]
                self._notify_conversion_status(inputs[0], "converting", [], out_path)
                render_report: dict = {}
                saved = process_single(
                    inputs[0],
                    out_path,
                    cfg,
                    link_context={
                        "source_path": inputs[0],
                        "output_path": out_path,
                        "document_map": document_output_map(plan),
                    },
                    report=render_report,
                )
                files = [saved] if saved else []
                entry_file = os.path.abspath(saved) if saved else ""
                errors_list = [] if saved else ["生成 HTML 失败。"]
                item_result = dict(item)
                item_result.update(
                    {
                        "path": saved or "",
                        "status": "warning" if render_report.get("warnings") else (
                            "success" if saved else "error"
                        ),
                        "warnings": render_report.get("warnings", []),
                    }
                )
                documents = [item_result]
                warnings_list.extend(render_report.get("warnings", []))
                self._notify_conversion_status(
                    inputs[0],
                    item_result["status"],
                    item_result["warnings"],
                    saved or out_path,
                )

            # Auto-open
            if auto_open and entry_file:
                webbrowser.open(_file_uri(entry_file))

            return {
                "success": len(files) > 0,
                "files": files,
                "errors": errors_list,
                "warnings": list(dict.fromkeys(warnings_list)),
                "documents": documents,
                "output_dir": actual_output_dir,
                "entry_file": entry_file,
            }
        except Exception as e:
            _logger.exception("转换失败")
            return {"success": False, "files": [], "errors": [str(e)]}

    # ── System ──────────────────────────────────────────────

    def open_file(self, path: str) -> None:
        """Open a file with the default system application."""
        if os.path.isfile(path):
            webbrowser.open(_file_uri(path))

    def open_directory(self, path: str) -> None:
        """Open a directory in the system file explorer."""
        if os.path.isdir(path):
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
