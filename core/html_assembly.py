"""Assemble a complete standalone HTML document from a renderer v2 envelope.

Phase 5D. The v2 adapter returns a body fragment plus resource channels
(`resources.styles` / `resources.scripts`); the page shell, the TOC and the
viewer wiring belong to core. This module performs that assembly for the v2
renderer path, while `core/converter.py` assembles the v1 rollback path inline.
Reader assets -- page shell, viewer script, theme chain, print sheet -- come from
`core/viewer_assets.py`, which is the only layer that knows where they live.

Deterministic injection order (mirrors the v1 order in `core/converter.py`, so a
later cutover swaps the resource source instead of changing page structure):

    <head>    viewer.css -> theme chain -> resources.styles (manifest order) -> print.css
    </body>   viewer.js -> numbering autostart -> per script entry: script -> boot

Every injected fragment is recorded in `injections` with its byte size, so the
standalone closure checker can report payload sizes without guessing which part
of the final document came from which resource.
"""

import logging
from html import escape

from core.config import (
    PLACEHOLDER_CONTENT,
    PLACEHOLDER_TITLE,
    PLACEHOLDER_TOC,
    normalize_template_name,
)
from core.toc import generate_toc_html
from core.viewer_assets import (
    shared_print_css_text,
    shared_viewer_js_text,
    theme_body_class,
    theme_css_chain,
    viewer_layout_css_text,
    viewer_shell_text,
)

_logger = logging.getLogger(__name__)

# Same wiring as the production path: the viewer owns the button and its state.
_NUMBERING_AUTOSTART = (
    "<script>"
    "document.addEventListener('DOMContentLoaded',function(){"
    "document.getElementById('btn-auto-numbering')?.click();"
    "});"
    "</script>"
)


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

    template_html = viewer_shell_text(resolved_template)
    if not template_html:
        raise ValueError(f"模板“{resolved_template}”缺少 viewer.html，无法装配。")
    for placeholder in (PLACEHOLDER_TITLE, PLACEHOLDER_CONTENT, PLACEHOLDER_TOC):
        if placeholder not in template_html:
            raise ValueError(f"模板“{resolved_template}”缺少占位符 {placeholder}，无法装配。")
    template_html = template_html.replace(
        "<body>", f'<body class="{theme_body_class(resolved_template)}">', 1
    )

    injections: list[dict] = []
    assembly_warnings: list[str] = []

    # ── <head>: viewer.css, theme chain, resource styles, print.css ──
    head_fragments: list[tuple[str, str, str | None]] = []
    viewer_css = viewer_layout_css_text(resolved_template)
    if viewer_css:
        head_fragments.append((f"<style>\n{viewer_css}\n</style>", "viewer-css", None))

    try:
        theme_css = theme_css_chain(resolved_template)
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

    print_css = shared_print_css_text()
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
    viewer_js = shared_viewer_js_text()
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
