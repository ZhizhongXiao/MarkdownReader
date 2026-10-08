"""Batch conversion planning, result collection, and index generation."""

import logging
import os
from typing import Protocol

from core.conversion_plan import (
    ConversionPlan,
    build_conversion_plan,
    document_output_map,
)
from core.fm import parse_front_matter
from core.index_builder import DEFAULT_INDEX_FILENAME, build_index

_logger = logging.getLogger(__name__)


class SingleDocumentConverter(Protocol):
    """Conversion callback injected by the owning process or IPC client."""

    def __call__(
        self,
        input_path: str,
        output_path: str,
        cfg: dict,
        link_context: dict[str, object],
        report: dict,
        *,
        renderer_options: dict | None = None,
    ) -> str | None: ...


def process_batch(
    inputs: list[str],
    output_dir: str,
    cfg: dict,
    single_converter: SingleDocumentConverter,
    source_root: str | None = None,
    index_filename: str = DEFAULT_INDEX_FILENAME,
    collection_name: str = "",
    plan: ConversionPlan | None = None,
    progress_callback=None,
    *,
    renderer_options: dict | None = None,
) -> list[dict]:
    """Convert every planned document and keep the established batch result contract."""
    if plan is None:
        plan = build_conversion_plan(
            inputs,
            output_dir,
            preserve_structure=bool(source_root),
        )
    link_map = document_output_map(plan)
    results: list[dict] = []

    for item in plan.get("items", []):
        input_path = item["source_path"]
        output_path = item["output_path"]
        if progress_callback:
            progress_callback(input_path, "converting", [], output_path)

        report: dict = {}
        try:
            saved = single_converter(
                input_path,
                output_path,
                cfg,
                {
                    "source_path": input_path,
                    "output_path": output_path,
                    "document_map": link_map,
                },
                report,
                renderer_options=renderer_options,
            )
        except Exception as error:
            _logger.error("转换失败：%s；原因：%s", input_path, error)
            if progress_callback:
                progress_callback(input_path, "error", [str(error)], output_path)
            continue

        if saved:
            try:
                with open(input_path, encoding="utf-8") as handle:
                    raw = handle.read()
                metadata, _ = parse_front_matter(raw)
            except Exception:
                metadata = {}

            warnings: list[str] = report.get("warnings", [])
            result = {
                "filename": item["output_relative"].replace(os.sep, "/"),
                "path": saved,
                "title": metadata.get("title")
                or os.path.splitext(os.path.basename(item["output_relative"]))[0],
                "author": metadata.get("author", ""),
                "date": metadata.get("date", ""),
                "tags": metadata.get("tags", []),
                "source_path": input_path,
                "output_path": saved,
                "status": "warning" if warnings else "success",
                "warnings": warnings,
            }
            results.append(result)
            if progress_callback:
                progress_callback(
                    input_path,
                    "warning" if warnings else "success",
                    warnings,
                    saved,
                )
        elif progress_callback:
            progress_callback(input_path, "error", ["生成 HTML 失败。"], output_path)

    if cfg.get("build_index", True):
        build_index(
            plan.get("output_dir", output_dir),
            results,
            filename=index_filename,
            collection_name=collection_name,
        )

    return results
