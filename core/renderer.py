"""MarkdownReader — Unified Markdown rendering entry point.

Dispatches to the configured engine (python or node).

Usage:
    from core.renderer import render_markdown
    html = render_markdown(md_text)           # uses config default
    html = render_markdown(md_text, "node")   # force Node engine
    html = render_markdown(md_text, "python") # force Python engine
"""

import logging

from core import config as _config_module

_logger = logging.getLogger(__name__)


def render_markdown(
    md_text: str,
    engine: str | None = None,
    context: dict | None = None,
) -> str:
    """Convert Markdown text to an HTML body fragment.

    Args:
        md_text: Raw Markdown source text (without front matter).
        engine: "python" or "node". If None, uses config.json default.

    Returns:
        HTML string (body fragment, no <html>/<body> tags).
    """
    if engine is None:
        cfg = _config_module.load_config()
        engine = cfg.get("markdown_engine", "python")

    if engine == "node":
        from core.renderer_node import render_markdown_node

        return render_markdown_node(md_text, context=context)
    else:
        from core.renderer_python import render_markdown as _python_render

        return _python_render(md_text)
