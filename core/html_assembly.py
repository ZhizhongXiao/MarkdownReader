"""Assemble a complete standalone HTML document from a renderer v2 envelope.

Phase 5D. The v2 adapter returns a body fragment plus resource channels
(`resources.styles` / `resources.scripts`); the page shell, the TOC and the
viewer wiring belong to core. This module performs that assembly **for the new
renderer path only**: `core/converter.py` still owns the production (v1) path and
is deliberately untouched, because production cutover is a separate checkpoint.

Deterministic injection order (mirrors the v1 order in `core/converter.py`, so a
later cutover swaps the resource source instead of changing page structure):

    <head>    viewer.css -> theme chain -> resources.styles (manifest order) -> print.css
    </body>   viewer.js -> numbering autostart -> per script entry: script -> boot

Every injected fragment is recorded in `injections` with its byte size, so the
standalone closure checker can report payload sizes without guessing which part
of the final document came from which resource.
"""

import logging
import os
from html import escape

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
from core.toc import generate_toc_html

_logger = logging.getLogger(__name__)

# Same wiring as the production path: the viewer owns the button and its state.
_NUMBERING_AUTOSTART = (
    "<script>"
    "document.addEventListener('DOMContentLoaded',function(){"
    "document.getElementById('btn-auto-numbering')?.click();"
    "});"
    "</script>"
)


def _theme_body_class(template_name: str) -> str:
    """Return the stable CSS class for the active template.

    TEMPORARY DUPLICATION of `core/converter.py::_theme_body_class`: Phase 5D
    proves the new assembler while the production converter stays byte-identical,
    so this shared helper is not unified here. Unify both into `core/config.py`
    at the production cutover checkpoint, where two real consumers exist.
    """
    safe_name = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(template_name)).strip("-")
    return f"theme-{safe_name or 'default'}"


def _read_text(path: str | None) -> str:
    """Return the file text, or an empty string when the file does not exist."""
    if not path or not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _byte_size(fragment: str) -> int:
    """Return the UTF-8 size of an injected fragment, as it lands in the file."""
    return len(fragment.encode("utf-8"))

def assemble_document(
    envelope: dict,
    *,
    title: str,
    template_name: str = "modern",
    numbering: bool = False,
) -> dict:
    """Assemble a standalone HTML document from a renderer v2 envelope.

    Args:
        envelope: A successful v2 envelope (`html`, `headings`, `resources`).
        title: Document title; escaped before it enters the page.
        template_name: Visual template id; resolved through the template chain.
        numbering: Auto-activate heading numbering in the viewer.

    Returns:
        `{"html", "injections", "assembly_warnings"}`; `injections` is the ordered
        ledger of what was written where (`position`, `label`, `id`, `bytes`).

    Raises:
        ValueError: The template is unusable or lacks a required placeholder.
    """
    resources = envelope.get("resources") or {}
    styles = resources.get("styles") or []
    scripts = resources.get("scripts") or []
    headings = envelope.get("headings") or []
    resolved_template = normalize_template_name(template_name)

    viewer_html_path = resolve_template_file(resolved_template, "viewer.html")
    if viewer_html_path is None:
        raise ValueError(f"模板“{resolved_template}”缺少 viewer.html，无法装配。")

    template_html = _read_text(viewer_html_path)
    for placeholder in (PLACEHOLDER_TITLE, PLACEHOLDER_CONTENT, PLACEHOLDER_TOC):
        if placeholder not in template_html:
            raise ValueError(f"模板“{resolved_template}”缺少占位符 {placeholder}，无法装配。")
    template_html = template_html.replace(
        "<body>", f'<body class="{_theme_body_class(resolved_template)}">', 1
    )

    injections: list[dict] = []
    assembly_warnings: list[str] = []

    # ── <head>: viewer.css, theme chain, resource styles, print.css ──
    head_fragments: list[tuple[str, str, str | None]] = []
    viewer_css = _read_text(resolve_template_file(resolved_template, "viewer.css"))
    if viewer_css:
        head_fragments.append((f"<style>\n{viewer_css}\n</style>", "viewer-css", None))

    try:
        theme_css = load_theme_chain(resolved_template)
    except Exception as error:  # 模板样式问题只降级，不阻断装配
        theme_css = ""
        message = f"加载模板样式链失败：{error}"
        assembly_warnings.append(message)
        _logger.warning(message)
    if theme_css:
        head_fragments.append((f"<style>\n{theme_css}\n</style>", "theme", None))

    for index, style in enumerate(styles):
        entry = style or {}
        css = str(entry.get("css") or "")
        if not css:
            continue
        resource_id = str(entry.get("id") or f"style-{index}")
        head_fragments.append((f"<style>\n{css}\n</style>", f"style:{resource_id}", resource_id))

    print_css = _read_text(get_shared_print_css_path())
    if print_css:
        head_fragments.append((f'<style media="print">\n{print_css}\n</style>', "print", None))

    if head_fragments:
        head_markup = "\n".join(fragment for fragment, _, _ in head_fragments)
        template_html = template_html.replace("</head>", head_markup + "\n</head>", 1)
        for fragment, label, resource_id in head_fragments:
            injections.append(
                {
                    "position": "head",
                    "label": label,
                    "id": resource_id,
                    "bytes": _byte_size(fragment),
                }
            )

    # ── </body>: viewer wiring, numbering, then on-demand resource scripts ──
    body_fragments: list[tuple[str, str, str | None]] = []
    viewer_js = _read_text(get_shared_viewer_js_path())
    if viewer_js:
        body_fragments.append((f"<script>\n{viewer_js}\n</script>", "viewer-js", None))
    if numbering:
        body_fragments.append((_NUMBERING_AUTOSTART, "numbering", None))

    for index, script in enumerate(scripts):
        entry = script or {}
        resource_id = str(entry.get("id") or f"script-{index}")
        payload = str(entry.get("script") or "")
        boot = str(entry.get("boot") or "")
        if payload:
            body_fragments.append(
                (f"<script>\n{payload}\n</script>", f"script:{resource_id}", resource_id)
            )
        if boot:
            body_fragments.append(
                (f"<script>\n{boot}\n</script>", f"boot:{resource_id}", resource_id)
            )

    if body_fragments:
        body_markup = "\n".join(fragment for fragment, _, _ in body_fragments)
        template_html = template_html.replace("</body>", body_markup + "\n</body>", 1)
        for fragment, label, resource_id in body_fragments:
            injections.append(
                {
                    "position": "body",
                    "label": label,
                    "id": resource_id,
                    "bytes": _byte_size(fragment),
                }
            )

    # ── Placeholders ──
    template_html = template_html.replace(PLACEHOLDER_TITLE, escape(str(title), quote=False))
    template_html = template_html.replace(PLACEHOLDER_CONTENT, str(envelope.get("html") or ""))
    template_html = template_html.replace(
        PLACEHOLDER_TOC, generate_toc_html(headings) if headings else ""
    )

    return {"html": template_html, "injections": injections, "assembly_warnings": assembly_warnings}
