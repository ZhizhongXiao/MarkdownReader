"""Markdown to standalone HTML converter.

Provides the three functions previously expected from main.py:
collect_markdown_files, process_single, process_batch.
"""

import logging
import os

from core.config import (
    PLACEHOLDER_CONTENT,
    PLACEHOLDER_TITLE,
    PLACEHOLDER_TOC,
    get_shared_print_css_path,
    get_shared_viewer_js_path,
    load_theme_chain,
    normalize_template_name,
    resolve_template_file,
)
from core.conversion_plan import (
    build_conversion_plan,
    collect_input_documents,
    document_output_map,
)
from core.fm import parse_front_matter
from core.index_builder import DEFAULT_INDEX_FILENAME, build_index
from core.renderer import render_markdown  # unified entry (python/node)
from core.toc import generate_toc_html

_logger = logging.getLogger(__name__)
_DOCUMENT_RENDER_ENGINE = "node"


def _theme_body_class(template_name: str) -> str:
    """Return a stable CSS class for the active template."""
    safe_name = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(template_name)).strip("-")
    return f"theme-{safe_name or 'default'}"


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
) -> str | None:
    """Convert a single Markdown file to a standalone HTML document.

    Args:
        input_path: Path to the .md source file.
        output_path: Where to write the .html output.
        cfg: Configuration dict (from load_config).

    Returns:
        The output path on success, or None on failure.
    """
    template_name = normalize_template_name(cfg.get("template", "modern"))
    configured_engine = cfg.get("markdown_engine", _DOCUMENT_RENDER_ENGINE)
    if configured_engine != _DOCUMENT_RENDER_ENGINE:
        _logger.warning(
            "已忽略 markdown_engine=%s；Markdown 正文统一由 Node 渲染。",
            configured_engine,
        )

    # 1. Read Markdown
    try:
        with open(input_path, "r", encoding="utf-8") as f:
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

    # 4. Render Markdown → HTML body
    render_result = render_markdown(
        body_md,
        engine=_DOCUMENT_RENDER_ENGINE,
        context=link_context,
    )
    if not isinstance(render_result, dict):
        _logger.error("Node 渲染器返回了无效结果。")
        return None
    html_body = render_result.get("html", "")
    headings = render_result.get("headings", [])
    render_assets = render_result.get("assets", {})
    render_warnings = render_result.get("warnings", [])
    if report is not None:
        report["warnings"] = list(render_warnings)

    # 5. Generate TOC
    numbering = cfg.get("numbering", False)
    toc_html = generate_toc_html(headings) if headings else ""

    # 6. Load template files via chain
    viewer_html_path = resolve_template_file(template_name, "viewer.html")
    viewer_css_path = resolve_template_file(template_name, "viewer.css")
    viewer_js_path = get_shared_viewer_js_path()
    print_css_path = get_shared_print_css_path()

    if viewer_html_path is None:
        _logger.error("模板“%s”缺少 viewer.html。", template_name)
        return None

    with open(viewer_html_path, "r", encoding="utf-8") as f:
        template_html = f.read()

    theme_class = _theme_body_class(template_name)
    template_html = template_html.replace("<body>", f'<body class="{theme_class}">', 1)

    # 7. Collect CSS (viewer.css + theme chain) → inject into <head>
    css_parts = []
    if viewer_css_path and os.path.isfile(viewer_css_path):
        with open(viewer_css_path, "r", encoding="utf-8") as f:
            css_parts.append(f.read())
    try:
        css_parts.append(load_theme_chain(template_name))
    except Exception as e:
        _logger.warning("加载模板样式链失败：%s", e)
    combined_css = "\n".join(css_parts)

    # 8. Collect JS → inject before </body>
    js_parts = []
    if viewer_js_path and os.path.isfile(viewer_js_path):
        with open(viewer_js_path, "r", encoding="utf-8") as f:
            js_parts.append(f.read())
    combined_js = "\n".join(js_parts)

    # 9. Collect print CSS
    print_css = ""
    if print_css_path and os.path.isfile(print_css_path):
        with open(print_css_path, "r", encoding="utf-8") as f:
            print_css = f.read()

    # ── Inject CSS into <head> ──────────────────────────────────
    head_fragments = []
    if combined_css:
        head_fragments.append(f"<style>\n{combined_css}\n</style>")
    katex_css = render_assets.get("css", "")
    if katex_css:
        head_fragments.append(f"<style>\n{katex_css}\n</style>")
    if print_css:
        head_fragments.append(f'<style media="print">\n{print_css}\n</style>')
    if head_fragments:
        template_html = template_html.replace("</head>", "\n".join(head_fragments) + "\n</head>", 1)

    # ── Numbering auto-activation (if enabled) ──────────────────
    numbering_js = ""
    if numbering:
        numbering_js = (
            "<script>"
            "document.addEventListener('DOMContentLoaded',function(){"
            "document.getElementById('btn-auto-numbering')?.click();"
            "});"
            "</script>"
        )

    # ── Inject JS before </body> ───────────────────────────────
    body_fragments = []
    if combined_js:
        body_fragments.append(f"<script>\n{combined_js}\n</script>")
    if numbering_js:
        body_fragments.append(numbering_js)
    if body_fragments:
        template_html = template_html.replace("</body>", "\n".join(body_fragments) + "\n</body>", 1)

    # 10. Fill placeholders
    template_html = template_html.replace(PLACEHOLDER_TITLE, title)
    template_html = template_html.replace(PLACEHOLDER_CONTENT, html_body)
    template_html = template_html.replace(PLACEHOLDER_TOC, toc_html)

    # 11. Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template_html)

    _logger.info("已生成：%s", output_path)
    return output_path


def process_batch(
    inputs: list[str],
    output_dir: str,
    cfg: dict,
    source_root: str | None = None,
    index_filename: str = DEFAULT_INDEX_FILENAME,
    collection_name: str = "",
    plan: dict | None = None,
    progress_callback=None,
) -> list[dict]:
    """Process multiple Markdown files.

    Args:
        inputs: List of .md file paths.
        output_dir: Directory to write HTML outputs.
        cfg: Configuration dict.
        source_root: Source directory used to preserve relative paths.
        index_filename: Generated batch index filename.
        collection_name: Source directory name displayed by the index.

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
        )

        if saved:
            # Extract metadata for index
            try:
                with open(input_path, "r", encoding="utf-8") as f:
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
