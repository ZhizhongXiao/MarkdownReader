"""Assemble a complete standalone HTML document from a renderer v2 envelope.

Phase 5D. The v2 adapter returns a body fragment plus resource channels
(`resources.styles` / `resources.scripts`); the page shell, the TOC and the
viewer wiring belong to core. This module performs that assembly for the v2
renderer path, while `core/converter.py` assembles the v1 rollback path inline.
Reader assets -- page shell, viewer script, theme bundle, print sheet -- come from
`core/viewer_assets.py`, which is the only layer that knows where they live.

Deterministic injection order (mirrors the v1 order in `core/converter.py`, so a
later cutover swaps the resource source instead of changing page structure):

    <head>    viewer.css -> theme bundle (base + every builtin) -> resources.styles
              (manifest order) -> print.css
    </body>   viewer.js -> numbering autostart -> per script entry: script -> boot

Every injected fragment is recorded in `injections` with its byte size, so the
standalone closure checker can report payload sizes without guessing which part
of the final document came from which resource. Each theme gets its own label
(`theme:<id>`), which is what makes "every builtin theme exactly once" checkable.

`assembly_warnings` is part of the return shape; since Phase 6C the theme payload
either assembles or raises (`validate_theme` plus a required `theme.css`), so it
stays empty and is reserved for a future degrade path.
"""

import logging
from html import escape

from core.config import (
    PLACEHOLDER_CONTENT,
    PLACEHOLDER_THEME_ID,
    PLACEHOLDER_THEME_MENU,
    PLACEHOLDER_TITLE,
    PLACEHOLDER_TOC,
    normalize_template_name,
)
from core.external_themes import resolve_theme_selection, theme_bundle
from core.toc import generate_toc_html
from core.viewer_assets import (
    builtin_theme_ids,
    shared_print_css_text,
    shared_viewer_js_text,
    theme_body_class,
    theme_menu_markup,
    validate_theme,
    viewer_layout_css_text,
    viewer_shell_text,
)

_logger = logging.getLogger(__name__)

# Same wiring as the v1 rollback path: the viewer owns the button and its state.
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
    external_themes: list[str] | None = None,
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
    # 不可用（不存在 / 循环继承 / 非可选）的主题必须在这里失败：装配期不再有"主题降级"
    # 这一说，否则会产出一份没有任何主题变量的文档（6B 起锁在 test_standalone_matrix）。
    validate_theme(resolved_template)

    template_html = viewer_shell_text()
    if not template_html:
        raise ValueError("缺少阅读器页面外壳（viewer/viewer.html），无法装配。")
    # 缺任一必需占位符都必须在装配期失败：外壳不完整不该产出"看起来对"的文档。
    # 6C 起 {{THEME_ID}}（默认主题）与 {{THEME_MENU}}（主题菜单）与标题、正文、目录同为必需。
    for placeholder in (
        PLACEHOLDER_TITLE,
        PLACEHOLDER_CONTENT,
        PLACEHOLDER_TOC,
        PLACEHOLDER_THEME_ID,
        PLACEHOLDER_THEME_MENU,
    ):
        if placeholder not in template_html:
            raise ValueError(f"模板“{resolved_template}”缺少占位符 {placeholder}，无法装配。")
    template_html = template_html.replace(
        "<body>", f'<body class="{theme_body_class(resolved_template)}">', 1
    )

    injections: list[dict] = []
    assembly_warnings: list[str] = []

    # ── <head>: viewer.css, theme chain, resource styles, print.css ──
    head_fragments: list[tuple[str, str, str | None]] = []
    viewer_css = viewer_layout_css_text()
    if viewer_css:
        head_fragments.append((f"<style>\n{viewer_css}\n</style>", "viewer-css", None))

    try:
        # ── Theme bundle (Phase 6C, extended by 7E) ──
        # base + 全部 builtin + 本文档选中的外置主题，各恰好一次；
        # 每套主题单独一条 label：漏掉一套或重复内嵌都能被指出是哪一套。
        selection = resolve_theme_selection(external_themes, default=resolved_template)
        assembly_warnings.extend(selection["warnings"])
        for entry in theme_bundle(selection):
            head_fragments.append(
                (f"<style>\n{entry['css']}\n</style>", f"theme:{entry['id']}", None)
            )
    except ValueError as error:
        raise ValueError(f"主题资源不可用：{error}") from error
    _logger.debug("已内嵌主题 bundle：base + %s", ", ".join(builtin_theme_ids()))

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
    # Phase 6C: the document's default theme is active in the markup, and the theme
    # menu is part of the shell, so neither depends on a script having run.
    template_html = template_html.replace(PLACEHOLDER_THEME_ID, resolved_template)
    template_html = template_html.replace(
        PLACEHOLDER_THEME_MENU, theme_menu_markup(selection["external_ids"])
    )

    return {"html": template_html, "injections": injections, "assembly_warnings": assembly_warnings}
