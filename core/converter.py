"""Markdown to standalone HTML converter.

Provides the three functions previously expected from main.py:
collect_markdown_files, process_single, process_batch.

Two renderer paths share everything up to the render context: v2 is the production
default (assembled by `core/html_assembly.py`) and v1 is the explicit rollback
(assembled inline below). Cutover C3 wired the v2 path, Cutover C4 made it the
default; see K16/K26.
"""

import logging
import os
from html import escape

from core.config import (
    PLACEHOLDER_CONTENT,
    PLACEHOLDER_THEME_ID,
    PLACEHOLDER_THEME_MENU,
    PLACEHOLDER_TITLE,
    PLACEHOLDER_TOC,
    PRODUCTION_RENDERER_VERSION,
    normalize_template_name,
)
from core.conversion_plan import (
    build_conversion_plan,
    collect_input_documents,
    document_output_map,
)
from core.external_themes import resolve_theme_selection, theme_bundle
from core.fm import parse_front_matter
from core.html_assembly import assemble_document
from core.index_builder import DEFAULT_INDEX_FILENAME, build_index
from core.renderer_node import render_markdown_node
from core.toc import generate_toc_html
from core.viewer_assets import (
    shared_print_css_text,
    shared_viewer_js_text,
    theme_body_class,
    theme_menu_markup,
    validate_theme,
    viewer_layout_css_text,
    viewer_shell_text,
)

_logger = logging.getLogger(__name__)

# v2 的 production 内部默认值（Cutover C3）：显式写下来，而不是依赖 renderer 当下的隐式默认，
# 这样 adapter 默认值将来变化不会悄悄改变 MarkdownReader。**不进 config.json**（Phase 8 才决定
# 哪些 renderer 选项成为产品配置）；timeout / retries / maxBytes 仍是 5C 的实现策略。
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
    """Write the assembled document and return its path (both paths share this)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template_html)

    _logger.info("已生成：%s", output_path)
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
    renderer_version: str = PRODUCTION_RENDERER_VERSION,
    renderer_options: dict | None = None,
) -> str | None:
    """Convert a single Markdown file to a standalone HTML document.

    Args:
        input_path: Path to the .md source file.
        output_path: Where to write the .html output.
        cfg: Configuration dict (from load_config).
        link_context: Rendering context from the conversion plan. When
            omitted, the source and output paths are derived from this call so
            relative resources still resolve.
        report: When given, receives the conversion warnings.
        renderer_version: ``"v1"`` or ``"v2"``; defaults to
            ``core.config.PRODUCTION_RENDERER_VERSION`` (the policy constant that
            a rollback flips). This is an **internal** parameter on purpose: it is
            not part of config.json yet (Cutover C3 / K26).
        renderer_options: Renderer options; only the v2 path honours them.
            ``None`` uses ``_V2_DEFAULT_OPTIONS``, supplied values are merged
            over it. The v1 path rejects non-empty options.

    Returns:
        The output path on success, or None on failure. When the output already
        exists and overwrite is disabled, the existing file is kept, a warning is
        recorded in ``report``, and that path is returned.
    """
    if os.path.exists(output_path) and not cfg.get("overwrite", False):
        warning = "目标文件已存在且未启用覆盖，已跳过：%s" % output_path
        _logger.warning(warning)
        if report is not None:
            report["warnings"] = [warning]
        return output_path

    template_name = normalize_template_name(cfg.get("template", "modern"))

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

    # 4. Render → assemble. v2 是生产默认（Cutover C4）；v1 只在显式选择时走，保留为回退。
    render_context = dict(link_context or {})
    render_context.setdefault("source_path", input_path)
    render_context.setdefault("output_path", output_path)

    if renderer_version == "v2":
        return _convert_v2(
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
    if renderer_version != "v1":
        # 未知版本不能静默按 v1 处理：那会让调用方以为自己的选择生效了。
        raise ValueError("renderer_version 只能是 'v1' 或 'v2'，收到：%r" % (renderer_version,))

    render_result = render_markdown_node(
        body_md,
        context=render_context,
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

    # 6. Load the reader assets through the asset layer (Phase 6A/6B)
    # 不可用（不存在 / 循环继承 / 非可选）的主题必须在这里失败，与拆分前一致。
    validate_theme(template_name)
    # 7E：本文档额外携带哪些已安装外置主题（config.json 的 external_themes）。
    selected_external = _selected_external_themes(cfg)
    # 7E/7G：bundle、菜单与 warning 都出自这一次解析，避免三处各自判断。
    selection = resolve_theme_selection(selected_external, default=template_name)
    if report is not None:
        report.setdefault("warnings", [])
        report["warnings"].extend(selection["warnings"])
    template_html = viewer_shell_text()
    if not template_html:
        _logger.error("阅读器外壳缺失：viewer/viewer.html。")
        return None

    template_html = template_html.replace(
        "<body>", f'<body class="{theme_body_class(template_name)}">', 1
    )
    # Phase 6C：默认主题在标记里就已生效，主题菜单也是 shell 的一部分，都不依赖脚本。
    template_html = template_html.replace(PLACEHOLDER_THEME_ID, template_name)
    template_html = template_html.replace(
        PLACEHOLDER_THEME_MENU, theme_menu_markup(selection["menu_ids"])
    )

    # 7. Collect CSS (viewer.css + 主题 bundle) → inject into <head>
    css_parts = []
    layout_css = viewer_layout_css_text()
    if layout_css:
        css_parts.append(layout_css)
    # Phase 6C：每份文档携带全部 builtin 主题；7E 起还带上本文档选中的外置主题。
    # 两条装配路径都走 theme_bundle()，因此 v1 回退与 v2 的主题载荷一致。
    css_parts.extend(entry["css"] for entry in theme_bundle(selection))
    combined_css = "\n".join(css_parts)

    # 8. Collect JS → inject before </body>
    combined_js = shared_viewer_js_text()

    # 9. Collect print CSS
    print_css = shared_print_css_text()

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
    template_html = template_html.replace(PLACEHOLDER_TITLE, escape(str(title), quote=False))
    template_html = template_html.replace(PLACEHOLDER_CONTENT, html_body)
    template_html = template_html.replace(PLACEHOLDER_TOC, toc_html)

    # 11. Write output
    return _write_output(output_path, template_html)


def _convert_v2(
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
    """Render with the v2 renderer and assemble with `core/html_assembly.py`.

    Reachable when a caller asks for ``renderer_version="v2"``
    (Cutover C3 / K26); the production default is v2 since Cutover C4. Failure semantics follow
    v1: a template that cannot be assembled is logged and becomes ``None`` (nothing
    written), while renderer or bridge failures keep their actionable exception --
    a missing artifact must not be swallowed into a silent no-output.
    """
    envelope = render_markdown_node(
        body_md,
        context=render_context,
        renderer_version="v2",
        options=_resolve_v2_options(renderer_options),
    )
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

    if report is not None:
        # renderer warnings 在前（网络降级、资源缺失），assembly warnings 在后。
        # 6C 起装配期不再有主题降级（不可用即失败），因此后者今天恒为空，保留通道。
        report["warnings"] = list(envelope.get("warnings") or []) + list(
            assembled.get("assembly_warnings") or []
        )

    return _write_output(output_path, assembled["html"])


def process_batch(
    inputs: list[str],
    output_dir: str,
    cfg: dict,
    source_root: str | None = None,
    index_filename: str = DEFAULT_INDEX_FILENAME,
    collection_name: str = "",
    plan: dict | None = None,
    progress_callback=None,
    *,
    renderer_version: str = PRODUCTION_RENDERER_VERSION,
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
        renderer_version: Forwarded to ``process_single``; defaults to the
            production policy (``core.config.PRODUCTION_RENDERER_VERSION``).
        renderer_options: Forwarded to ``process_single`` (only v2 honours them).

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
                renderer_version=renderer_version,
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
