"""Bridge API exposed to the GUI's JavaScript context.

All methods are callable from JS via `pywebview.api.xxx()`.
This layer is thin — it only marshals data and delegates to core.
"""

import json
import logging
import os
import sys
import webbrowser

from core.config import (
    CONFIG_FILENAME,
    PROJECT_ROOT,
    TEMPLATES_DIR,
    load_config,
    normalize_template_name,
)
from core.conversion_plan import build_conversion_plan, document_output_map

_logger = logging.getLogger("gui")


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


class BridgeApi:
    """Public API exposed to pywebview's JavaScript context."""

    def __init__(self) -> None:
        self._window = None

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

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        paths = askopenfilenames(
            title="选择一个或多个 Markdown 文件",
            filetypes=[("Markdown", "*.md *.markdown"), ("All Files", "*.*")],
        )
        root.destroy()
        return list(paths) if paths else []

    def select_input_file(self) -> str:
        """Backward-compatible single-file wrapper."""
        paths = self.select_input_files()
        return paths[0] if paths else ""

    def select_input_directory(self) -> str:
        """Open a folder dialog to select a directory of .md files."""
        from tkinter import Tk
        from tkinter.filedialog import askdirectory

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

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = askdirectory(title="选择输出目录")
        root.destroy()
        return path if path else ""

    def prepare_conversion(
        self,
        inputs_json: str = "[]",
        output_dir: str = "",
        preserve_structure: bool = False,
    ) -> dict:
        """Expand inputs and return a read-only conversion plan for the GUI."""
        try:
            paths = json.loads(inputs_json) if isinstance(inputs_json, str) else inputs_json
            if not isinstance(paths, list):
                raise ValueError("输入路径必须是数组。")
            if not output_dir:
                output_dir = load_config().get("output", "output")
            return build_conversion_plan(paths, output_dir, preserve_structure)
        except Exception as exc:
            _logger.exception("生成转换预检清单失败")
            return {
                "inputs": [],
                "items": [],
                "source_root": "",
                "output_dir": output_dir or "output",
                "warnings": [],
                "errors": [str(exc)],
                "counts": {"selected": 0, "directory": 0, "dependency": 0, "total": 0},
            }

    # ── Template ────────────────────────────────────────────

    def get_templates(self) -> list[str]:
        """Return list of available template names."""
        names = []
        if os.path.isdir(TEMPLATES_DIR):
            for entry in os.listdir(TEMPLATES_DIR):
                full = os.path.join(TEMPLATES_DIR, entry)
                if os.path.isdir(full) and os.path.isfile(
                    os.path.join(full, "metadata.json")
                ):
                    try:
                        with open(os.path.join(full, "metadata.json"), "r", encoding="utf-8") as f:
                            metadata = json.load(f)
                    except Exception:
                        metadata = {}
                    if not metadata.get("hidden", False):
                        names.append(entry)
        return sorted(names) if names else ["modern"]

    # ── Config ──────────────────────────────────────────────

    def get_config(self) -> dict:
        """Return full merged configuration."""
        return load_config()

    def set_config(self, key: str, value) -> None:
        """Update a single config key and persist to config.json."""
        self.set_configs({key: value})

    def set_configs(self, overrides: dict) -> None:
        """Update multiple config keys and persist to config.json."""
        cfg = load_config()
        cfg.update(overrides)
        if "input" in cfg:
            cfg["input"] = _normalize_input_root(cfg["input"])
        if "output" in cfg:
            cfg["output"] = _normalize_config_path(str(cfg["output"]))
        if "template" in cfg:
            cfg["template"] = normalize_template_name(cfg["template"])
        self._write_json(cfg)

    def _write_json(self, cfg: dict) -> None:
        """Write a flat config dict back to config.json."""
        path = os.path.join(PROJECT_ROOT, CONFIG_FILENAME)
        data = {
            "build": {
                "input": cfg.get("input", ""),
                "template": cfg.get("template", "modern"),
                "output": cfg.get("output", "output"),
                "markdown_engine": cfg.get("markdown_engine", "node"),
            },
            "document": {
                "theme": cfg.get("theme", "auto"),
                "numbering": bool(cfg.get("numbering", False)),
            },
            "features": {
                "copy_assets": bool(cfg.get("copy_assets", True)),
                "build_index": bool(cfg.get("build_index", True)),
                "auto_open": bool(cfg.get("auto_open", True)),
                "preserve_structure": bool(cfg.get("preserve_structure", False)),
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        _logger.info("配置已保存到 %s。", CONFIG_FILENAME)

    # ── Conversion ──────────────────────────────────────────

    def convert(
        self,
        inputs_json: str = '["samples/demo.md"]',
        output_dir: str = "",
        template: str = "modern",
        overwrite: bool = False,
        build_index: bool = True,
        verbose: bool = False,
        auto_open: bool = False,
        preserve_structure: bool = False,
    ) -> dict:
        """Run conversion and return a result dict.

        Args:
            inputs_json: JSON array of file/directory paths.
            output_dir: Output directory (defaults to config value).
            template: Template name.
            overwrite: Overwrite existing files.
            build_index: Generate index.html.
            verbose: Detailed logging.
            auto_open: Open HTML in browser after generation.
            preserve_structure: Recreate source subdirectories under a
                source-name-HTML output directory.

        Returns:
            {"success": bool, "files": [...], "errors": [...]}
        """
        try:
            from core.converter import process_batch, process_single
            from core.index_builder import make_index_filename
        except Exception as e:
            return {"success": False, "files": [], "errors": [str(e)]}

        paths = json.loads(inputs_json) if isinstance(inputs_json, str) else inputs_json

        if not output_dir:
            output_dir = load_config().get("output", "output")

        # Build CLI overrides
        overrides = {
            "template": normalize_template_name(template),
            "output": output_dir,
            "overwrite": overwrite,
            "build_index": build_index,
            "verbose": verbose,
            "preserve_structure": preserve_structure,
        }

        try:
            cfg = load_config(cli_overrides=overrides)
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
                webbrowser.open(entry_file)

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
            webbrowser.open(path)

    def open_directory(self, path: str) -> None:
        """Open a directory in the system file explorer."""
        if os.path.isdir(path):
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
