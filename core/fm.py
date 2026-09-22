"""Front Matter parser for Markdown files.

Parses YAML front matter blocks (delimited by --- at the start of a file)
and returns a dictionary of metadata fields. PyYAML is a runtime dependency, so
front matter means the same thing in a source checkout and in a packaged build.
"""

import logging

import yaml

_logger = logging.getLogger(__name__)


def parse_front_matter(md_text: str) -> tuple[dict, str]:
    """Parse YAML front matter from the beginning of a Markdown string.

    Front matter is a block delimited by --- at the very start of the file
    and a closing --- on its own line. A single leading UTF-8 BOM is
    ignored, because files saved by Windows editors often carry one.

    Args:
        md_text: Raw Markdown text (may or may not have front matter).

    Returns:
        A tuple of (metadata_dict, remaining_markdown).
        If no front matter is found, returns ({}, md_text).
    """
    if md_text.startswith("\ufeff"):
        md_text = md_text[1:]

    if not md_text.startswith("---"):
        return {}, md_text

    lines = md_text.splitlines()
    if len(lines) < 3:
        return {}, md_text

    # Find the closing ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        _logger.warning("Front Matter 已找到起始分隔线，但缺少结束分隔线。")
        return {}, md_text

    # A block scalar may legally end with a newline, and splitlines dropped it,
    # so the YAML text gets one back before it is handed to the parser.
    yaml_text = "\n".join(lines[1:end_idx]) + "\n"

    metadata = {}
    try:
        parsed = yaml.safe_load(yaml_text)
        if isinstance(parsed, dict):
            metadata = parsed
    except Exception as e:
        # Malformed front matter is a page-level problem, not a reason to stop the
        # conversion: the reader still gets its Markdown.
        _logger.warning("Front Matter YAML 解析失败：%s", e)

    remaining = "\n".join(lines[end_idx + 1 :])
    return metadata, remaining
