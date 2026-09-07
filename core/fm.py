"""Front Matter parser for Markdown files.

Parses YAML front matter blocks (delimited by --- at the start of a file)
and returns a dictionary of metadata fields.
"""

import logging

_logger = logging.getLogger(__name__)

# Detect YAML parser availability
try:
    import yaml as _yaml_module

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False
    _yaml_module = None  # type: ignore


def parse_front_matter(md_text: str) -> tuple[dict, str]:
    """Parse YAML front matter from the beginning of a Markdown string.

    Front matter is a block delimited by --- at the very start of the file
    and a closing --- on its own line.

    Args:
        md_text: Raw Markdown text (may or may not have front matter).

    Returns:
        A tuple of (metadata_dict, remaining_markdown).
        If no front matter is found, returns ({}, md_text).
    """
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

    yaml_text = "\n".join(lines[1:end_idx])

    metadata = {}
    try:
        if _HAS_YAML and _yaml_module is not None:
            parsed = _yaml_module.safe_load(yaml_text)
        else:
            parsed = _parse_simple_yaml(yaml_text)
        if isinstance(parsed, dict):
            metadata = parsed
    except Exception as e:
        _logger.warning("Front Matter YAML 解析失败：%s", e)

    remaining = "\n".join(lines[end_idx + 1 :])
    return metadata, remaining


def _parse_simple_yaml(yaml_text: str) -> dict:
    """Minimal YAML key: value parser (no PyYAML dependency).

    Supports: key: value, "quoted values", '- list items'.
    """
    result: dict = {}
    lines = yaml_text.splitlines()
    last_key: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- "):
            if last_key is not None:
                if last_key not in result:
                    result[last_key] = []
                val = stripped[2:].strip().strip('"').strip("'")
                result[last_key].append(val)
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            elif val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            if val == "":
                last_key = key
                continue
            result[key] = val
            last_key = key

    return result
