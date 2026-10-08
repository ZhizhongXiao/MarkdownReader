"""GUI conversion orchestration behind the stable pywebview bridge."""

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from typing import NotRequired, TypedDict

from core.batch import process_batch as process_batch_core
from core.config import load_config
from core.conversion_plan import ConversionPlan, build_conversion_plan, document_output_map
from core.viewer_assets import normalize_theme_id
from gui.services.backend_client import BackendClient, BackendClientError, BackendClientPort

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
        backend_client: BackendClientPort | None = None,
    ) -> None:
        self._notify_status = notify_status
        self._open_file_uri = open_file_uri
        self._bootstrap_template = bootstrap_template
        self._backend = backend_client or BackendClient()

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
        """Plan locally and render every document through the shared Backend host."""
        try:
            from core.index_builder import make_index_filename
        except Exception as error:
            return {"success": False, "files": [], "errors": [str(error)]}

        request = request or {}
        paths = request.get("inputs", [])
        if not isinstance(paths, list):
            return {"success": False, "files": [], "errors": ["输入路径必须是数组。"]}
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

            self._backend.ensure_backend()
            is_batch = len(inputs) > 1 or os.path.isdir(paths[0])
            actual_output_dir = plan["output_dir"]
            entry_file = ""
            documents: list[dict] = []
            files: list[str] = []
            warnings_list = list(plan.get("warnings", []))
            link_map = document_output_map(plan)
            errors_list: list[str] = []

            if is_batch:
                source_name = ""
                if len(paths) == 1 and os.path.isdir(paths[0]):
                    selected_root = os.path.abspath(paths[0])
                    source_name = os.path.basename(os.path.normpath(selected_root))

                index_filename = make_index_filename(source_name)
                results = process_batch_core(
                    inputs,
                    actual_output_dir,
                    cfg,
                    self._convert_batch_document,
                    source_root=plan.get("source_root") or None,
                    index_filename=index_filename,
                    collection_name=source_name,
                    plan=plan,
                    progress_callback=self._notify_status,
                )
                files = [str(result.get("path", "")) for result in results]
                documents = results
                for result in results:
                    warnings_list.extend(result.get("warnings", []))
                index_path = os.path.join(actual_output_dir, index_filename)
                if build_index and os.path.isfile(index_path):
                    entry_file = os.path.abspath(index_path)
                elif files:
                    entry_file = os.path.abspath(files[0])
                if len(results) != len(items):
                    errors_list = [f"有 {len(items) - len(results)} 个文档生成失败。"]
            else:
                item = items[0]
                input_path = item["source_path"]
                out_path = item["output_path"]
                self._notify_status(input_path, "converting", [], out_path)
                item_result = dict(item)
                conversion_error = ""
                try:
                    report: dict = {}
                    saved = self._convert_batch_document(
                        input_path,
                        out_path,
                        cfg,
                        {
                            "source_path": input_path,
                            "output_path": out_path,
                            "document_map": link_map,
                        },
                        report,
                    )
                    item_warnings: list[str] = report.get("warnings", [])
                except Exception as error:
                    conversion_error = str(error)
                    errors_list = [conversion_error]
                    saved = ""
                    item_warnings = []
                if saved:
                    files = [saved]
                    entry_file = os.path.abspath(saved)
                status = "warning" if item_warnings else ("success" if saved else "error")
                item_result.update(
                    {
                        "path": saved,
                        "status": status,
                        "warnings": item_warnings or (
                            [conversion_error] if conversion_error else []
                        ),
                    }
                )
                documents = [item_result]
                if not errors_list and not saved:
                    errors_list = ["生成 HTML 失败。"]
                warnings_list.extend(item_warnings)
                if saved:
                    self._notify_status(input_path, status, item_warnings, saved)
                elif conversion_error:
                    self._notify_status(input_path, "error", [conversion_error], out_path)

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

    def backend_status(self) -> dict[str, object]:
        """Return the shared headless Backend status, ensuring it is available."""
        return self._backend.status()

    def _convert_batch_document(
        self,
        input_path: str,
        output_path: str,
        cfg: dict,
        link_context: dict[str, object],
        report: dict,
        *,
        renderer_options: dict | None = None,
    ) -> str:
        document_map = link_context.get("document_map")
        if not isinstance(document_map, dict) or any(
            not isinstance(source, str) or not isinstance(target, str)
            for source, target in document_map.items()
        ):
            raise BackendClientError("invalid_conversion_context", "批次文档映射格式无效。")
        result = self._backend.request_convert(
            {
                "input_path": input_path,
                "output_path": output_path,
                "overwrite": bool(cfg.get("overwrite", False)),
                "offline": bool(
                    renderer_options is not None
                    and renderer_options.get("fetch_remote_resources") is False
                ),
                "template": normalize_theme_id(str(cfg.get("template", self._bootstrap_template))),
                "document_map": document_map,
            }
        )
        saved = result.get("output_path")
        warnings = result.get("warnings", [])
        if not isinstance(saved, str) or not saved:
            raise BackendClientError(
                "invalid_backend_response", "Backend 转换结果缺少 output_path。",
            )
        if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
            raise BackendClientError(
                "invalid_backend_response", "Backend 转换结果中的 warnings 格式无效。",
            )
        report["warnings"] = warnings
        return saved
