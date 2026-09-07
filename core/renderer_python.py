"""Markdown to HTML renderer.

Converts Markdown text to an HTML body fragment using the markdown library
with extensions for code highlighting and enhanced formatting.
"""

from core.toc import slugify_unicode


def render_markdown(md_text: str) -> str:
    """Convert Markdown text to an HTML body fragment.

    Args:
        md_text: Raw Markdown source text.

    Returns:
        HTML string representing the rendered Markdown content (without
        surrounding <html> or <body> tags).
    """
    import markdown  # lazy import — markdown is heavy (pymdown-extensions, pygments)

    extensions = [
        "pymdownx.highlight",
        "pymdownx.superfences",
        "pymdownx.inlinehilite",
        "pymdownx.betterem",
        "pymdownx.tilde",
        "pymdownx.tasklist",
        "pymdownx.arithmatex",
        "toc",
        "tables",
        "fenced_code",
        "codehilite",
    ]

    extension_configs = {
        "pymdownx.highlight": {
            "linenums": False,
        },
        "pymdownx.arithmatex": {
            "generic": True,
            "smart_dollar": True,
        },
        "codehilite": {
            "guess_lang": False,
        },
        "toc": {
            "slugify": slugify_unicode,
            "separator": "-",
        },
    }

    md = markdown.Markdown(
        extensions=extensions,
        extension_configs=extension_configs,
        output_format="html",
    )

    html_content = md.convert(md_text)

    return html_content
