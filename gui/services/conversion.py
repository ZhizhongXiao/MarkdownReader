"""GUI conversion orchestration behind the stable pywebview bridge."""

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from typing import NotRequired, TypedDict

from core.config import load_config
from core.conversion_plan import ConversionPlan, build_conversion_plan, document_output_map
from core.viewer_assets import normalize_theme_id

_logger = logging.getLogger("gui")


class ConversionResult(TypedDict):
    success: bool
    files: list[str]
    errors: list[str]
    warnings: NotRequired[list[str]]
    documents: NotRequired[Sequence[Mapping[str, object]]]
    output_dir: NotRequired[str]
    entry_file: NotRequired[str]


def _refused_plan() -> ConversionPlan:
    return {
        "inputs": [],
        "items": [],
        "source_root": "",
        "output_dir": "",
        "warnings": [],
        "errors": ["移除用户数据已开始，本次操作被拒绝。"],
        "counts": {"selected": 0, "directory": 0, "dependency": 0, "total": 0},
    }


class ConversionService:
    """Build plans and generate the HTML requested by the GUI."""

    def __init__(
        self,
        notify_status: Callable[[str, str, list[str] | None, str], None],
        open_file_uri: Callable[[str], None],
        bootstrap_template: str,
    ) -> None:
        self._notify_status = notify_status
        self._open_file_uri = open_file_uri
        self._bootstrap_template = bootstrap_template

    def prepare(self, request: dict | None = None) -> ConversionPlan:
        """Return the read-only plan for the GUI's structured conversion request."""
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

    def convert(self, request: dict | None = None) -> ConversionResult:
        """Convert one structured request; the facade owns terminal-operation gating."""
        try:
            from core.converter import process_batch, process_single
            from core.index_builder import make_index_filename
        except Exception as error:
            return {"success": False, "files": [], "errors": [str(error)]}

        request = request or {}
        paths = request.get("inputs", [])
        output_dir = request.get("output_dir", "")
        overwrite = bool(request.get("overwrite", False))
        build_index = bool(request.get("build_index", True))
        auto_open = bool(request.get("auto_open", False))
        preserve_structure = bool(request.get("preserve_structure", False))

        if not output_dir:
            output_dir = load_config().get("output", "output")

        overrides = {
            "template": normalize_theme_id(self._bootstrap_template),
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
                    progress_callback=self._notify_status,
                )
                files = [result.get("path", "") for result in results]
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
                self._notify_status(inputs[0], "converting", [], out_path)
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
                item_warnings: list[str] = render_report.get("warnings", [])
                status = "warning" if item_warnings else ("success" if saved else "error")
                item_result.update(
                    {
                        "path": saved or "",
                        "status": status,
                        "warnings": item_warnings,
                    }
                )
                documents = [item_result]
                warnings_list.extend(item_warnings)
                self._notify_status(inputs[0], status, item_warnings, saved or out_path)

            if auto_open and entry_file:
                self._open_file_uri(entry_file)

            return {
                "success": len(files) > 0,
                "files": files,
                "errors": errors_list,
                "warnings": list(dict.fromkeys(warnings_list)),
                "documents": documents,
                "output_dir": actual_output_dir,
                "entry_file": entry_file,
            }
        except Exception as error:
            _logger.exception("转换失败")
            return {"success": False, "files": [], "errors": [str(error)]}
