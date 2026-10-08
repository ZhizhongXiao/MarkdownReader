"""Markdown to standalone HTML converter.

Provides the three functions previously expected from main.py:
collect_markdown_files, process_single, process_batch.

Markdown is rendered by the v2 adapter and assembled by `core/html_assembly.py`.
"""

import logging
import os
import time

from core.config import (
    normalize_template_name,
)
from core.conversion_plan import (
    ConversionPlan,
    build_conversion_plan,
    collect_input_documents,
    document_output_map,
)
from core.fm import parse_front_matter
from core.html_assembly import assemble_document
from core.index_builder import DEFAULT_INDEX_FILENAME, build_index
from core.renderer_node import render_markdown_node

_logger = logging.getLogger(__name__)

# v2 的 production 内部默认值（Cutover C3）：显式写下来，而不是依赖 renderer 当下的隐式默认，
# 这样 adapter 默认值将来变化不会悄悄改变 MarkdownReader。**不进 config.json**：Phase 8 已决定
# renderer protocol options 保持内部运行策略，不成为用户偏好；timeout / retries / maxBytes 仍是
# 5C 的实现策略。
_V2_DEFAULT_OPTIONS = {"math": True, "fetch_remote_resources": True}


def _resolve_v2_options(overrides: dict | None) -> dict:
    """Return the v2 render options: internal defaults plus explicit overrides."""
    options = dict(_V2_DEFAULT_OPTIONS)
    if overrides:
        options.update(overrides)
    return options


def _selected_external_themes(cfg: dict) -> list[str]:
    """Return the installed user themes this document should carry (Phase 7E).

    Builtin themes are always bundled; this is only the per-document selection from
    config.json. Ids that are not installed are ignored further down, by the registry.
    """
    return [str(item) for item in (cfg.get("external_themes") or [])]


def _write_output(output_path: str, template_html: str) -> str:
    """Write the assembled document and return its path (both paths share this).

    ``newline="\\n"`` is deliberate (Phase 9B2-B): the markup is assembled with LF and the file is a
    durable artifact -- diffs, checksums and the committed demo specimen compare its bytes -- so the
    platform default must not rewrite every line break into CRLF on Windows.
    """
    started = time.perf_counter()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(template_html)

    _logger.info("已生成：%s", output_path)
    _logger.debug(
        "timing stage=output_write elapsed_ms=%.2f",
        (time.perf_counter() - started) * 1000,
    )
    return output_path


# ── KaTeX resource fragments (centralised for future local embedding) ──


def collect_markdown_files(paths: list[str]) -> list[str]:
    """Collect all .md files from a list of paths (files or directories).

    Args:
        paths: List of file or directory paths.

    Returns:
        Deduplicated list of absolute .md file paths, sorted.
    """
    documents, warnings, errors = collect_input_documents(paths)
    for message in warnings:
        _logger.warning(message)
    for message in errors:
        _logger.warning(message)
    return [item["source_path"] for item in documents]


def process_single(
    input_path: str,
    output_path: str,
    cfg: dict,
    link_context: dict | None = None,
    report: dict | None = None,
    *,
    renderer_options: dict | None = None,
) -> str | None:
    """Convert a single Markdown file to a standalone HTML document.

    Args:
        input_path: Path to the .md source file.
        output_path: Where to write the .html output.
        cfg: Configuration dict (from load_config).
        link_context: Rendering context from the conversion plan. When omitted,
            the source and output paths are derived from this call so relative
            resources still resolve.
        report: When given, receives the conversion warnings.
        renderer_options: Options passed to the v2 renderer. ``None`` uses
            ``_V2_DEFAULT_OPTIONS``; supplied values are merged over those defaults.

    Returns:
        The output path on success, or None on failure. When the output already
        exists and overwrite is disabled, the existing file is kept, a warning is
        recorded in ``report``, and that path is returned.
    """
    if os.path.exists(output_path) and not cfg.get("overwrite", False):
        warning = f"目标文件已存在且未启用覆盖，已跳过：{output_path}"
        _logger.warning(warning)
        if report is not None:
            report["warnings"] = [warning]
        return output_path

    template_name = normalize_template_name(cfg.get("template", "modern"))

    # 1. Read Markdown
    try:
        with open(input_path, encoding="utf-8") as f:
            md_text = f.read()
    except Exception as e:
        _logger.error("读取文件失败：%s；原因：%s", input_path, e)
        return None

    # 2. Parse front matter
    metadata, body_md = parse_front_matter(md_text)

    # 3. Determine title
    title = (
        cfg.get("title")
        or metadata.get("title")
        or os.path.splitext(os.path.basename(input_path))[0]
    )

    render_context = dict(link_context or {})
    render_context.setdefault("source_path", input_path)
    render_context.setdefault("output_path", output_path)

    return _convert_document(
        body_md=body_md,
        render_context=render_context,
        title=title,
        template_name=template_name,
        numbering=bool(cfg.get("numbering", False)),
        external_themes=_selected_external_themes(cfg),
        output_path=output_path,
        renderer_options=renderer_options,
        report=report,
    )

def _convert_document(
    *,
    body_md: str,
    render_context: dict,
    title: str,
    template_name: str,
    numbering: bool,
    external_themes: list[str] | None,
    output_path: str,
    renderer_options: dict | None,
    report: dict | None,
) -> str | None:
    """Render and assemble a document through the supported v2 pipeline."""
    conversion_started = time.perf_counter()
    render_started = time.perf_counter()
    envelope = render_markdown_node(
        body_md,
        context=render_context,
        options=_resolve_v2_options(renderer_options),
    )
    _logger.debug(
        "timing stage=renderer_total elapsed_ms=%.2f",
        (time.perf_counter() - render_started) * 1000,
    )
    assembly_started = time.perf_counter()
    try:
        assembled = assemble_document(
            envelope,
            title=title,
            template_name=template_name,
            numbering=numbering,
            external_themes=external_themes,
        )
    except ValueError as error:
        _logger.error("v2 装配失败：%s；原因：%s", output_path, error)
        return None
    finally:
        _logger.debug(
            "timing stage=html_assembly elapsed_ms=%.2f",
            (time.perf_counter() - assembly_started) * 1000,
        )

    if report is not None:
        # renderer warnings 在前（网络降级、资源缺失），assembly warnings 在后。
        # 后者携带非致命的主题选择提示（Phase 7E）：配置里已不存在的主题被忽略，文档默认的
        # 外置主题被补进 selection；不安全或损坏的主题载荷仍是硬失败（装配期抛错）。
        report["warnings"] = list(envelope.get("warnings") or []) + list(
            assembled.get("assembly_warnings") or []
        )

    result = _write_output(output_path, assembled["html"])
    _logger.debug(
        "timing stage=conversion_pipeline elapsed_ms=%.2f",
        (time.perf_counter() - conversion_started) * 1000,
    )
    return result


def process_batch(
    inputs: list[str],
    output_dir: str,
    cfg: dict,
    source_root: str | None = None,
    index_filename: str = DEFAULT_INDEX_FILENAME,
    collection_name: str = "",
    plan: ConversionPlan | None = None,
    progress_callback=None,
    *,
    renderer_options: dict | None = None,
) -> list[dict]:
    """Process multiple Markdown files.

    Args:
        inputs: List of .md file paths.
        output_dir: Directory to write HTML outputs.
        cfg: Configuration dict.
        source_root: Source directory used to preserve relative paths.
        index_filename: Generated batch index filename.
        collection_name: Source directory name displayed by the index.
        renderer_options: Forwarded to ``process_single``.

    Returns:
        List of result dicts with keys: filename, title, author, date, tags.
    """
    results: list[dict] = []
    if plan is None:
        plan = build_conversion_plan(
            inputs,
            output_dir,
            preserve_structure=bool(source_root),
        )
    link_map = document_output_map(plan)

    for item in plan.get("items", []):
        input_path = item["source_path"]
        out_path = item["output_path"]
        filename = item["output_relative"]
        if progress_callback:
            progress_callback(input_path, "converting", [], out_path)

        render_report: dict = {}
        try:
            saved = process_single(
                input_path,
                out_path,
                cfg,
                link_context={
                    "source_path": input_path,
                    "output_path": out_path,
                    "document_map": link_map,
                },
                report=render_report,
                renderer_options=renderer_options,
            )
        except Exception as e:
            _logger.error("转换失败：%s；原因：%s", input_path, e)
            if progress_callback:
                progress_callback(input_path, "error", [str(e)], out_path)
            continue

        if saved:
            # Extract metadata for index
            try:
                with open(input_path, encoding="utf-8") as f:
                    raw = f.read()
                meta, _ = parse_front_matter(raw)
            except Exception:
                meta = {}

            results.append(
                {
                    "filename": filename.replace(os.sep, "/"),
                    "path": saved,
                    "title": meta.get("title") or os.path.splitext(os.path.basename(filename))[0],
                    "author": meta.get("author", ""),
                    "date": meta.get("date", ""),
                    "tags": meta.get("tags", []),
                    "source_path": input_path,
                    "output_path": saved,
                    "status": "warning" if render_report.get("warnings") else "success",
                    "warnings": render_report.get("warnings", []),
                }
            )
            if progress_callback:
                progress_callback(
                    input_path,
                    "warning" if render_report.get("warnings") else "success",
                    render_report.get("warnings", []),
                    saved,
                )
        elif progress_callback:
            progress_callback(input_path, "error", ["生成 HTML 失败。"], out_path)

    # Generate index if enabled
    if cfg.get("build_index", True):
        build_index(
            plan.get("output_dir", output_dir),
            results,
            filename=index_filename,
            collection_name=collection_name,
        )

    return results
