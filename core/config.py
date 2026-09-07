"""MDViewer configuration management.

Handles loading config.json, merging with CLI overrides, and providing
template paths with inheritance chain resolution.
"""

import json
import logging
import os
import sys

_logger = logging.getLogger(__name__)

# Source root when running from Python.
_SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_bundle_root() -> str:
    """Return the directory containing bundled read-only application assets."""
    return os.path.abspath(getattr(sys, "_MEIPASS", _SOURCE_ROOT))


def get_application_dir() -> str:
    """Return the EXE directory when frozen, otherwise the source root."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _SOURCE_ROOT


BUNDLE_ROOT = get_bundle_root()

# Kept as the writable application root for existing callers.
PROJECT_ROOT = get_application_dir()

# Templates root directory
TEMPLATES_DIR = os.path.join(BUNDLE_ROOT, "templates")

# Shared files (all templates use these)
_SHARED_VIEWER_JS = os.path.join(TEMPLATES_DIR, "viewer.js")
_SHARED_PRINT_CSS = os.path.join(TEMPLATES_DIR, "print.css")

# Template placeholders
PLACEHOLDER_TITLE = "{{TITLE}}"
PLACEHOLDER_TOC = "{{TOC}}"
PLACEHOLDER_CONTENT = "{{CONTENT}}"

# Default output extension
DEFAULT_OUTPUT_EXTENSION = ".html"

# Runtime configuration file
CONFIG_FILENAME = "config.json"

# Default configuration values
_DEFAULTS: dict = {
    "input": "",
    "template": "modern",
    "output": "output",
    "theme": "auto",
    "numbering": False,
    "copy_assets": True,
    "build_index": True,
    "auto_open": True,
    "overwrite": False,
    "preserve_structure": False,
    "title": None,
    "verbose": False,
    "markdown_engine": "node",
}

_TEMPLATE_ALIASES: dict[str, str] = {
    "mordern": "modern",
}


def normalize_template_name(template_name: str | None) -> str:
    """Normalize user-facing template aliases to canonical template ids."""
    name = str(template_name or _DEFAULTS["template"]).strip().lower()
    return _TEMPLATE_ALIASES.get(name, name)


def _find_config(config_path: str | None = None) -> str | None:
    """Find the config.json file."""
    if config_path and os.path.isfile(config_path):
        return config_path
    default_path = os.path.join(PROJECT_ROOT, CONFIG_FILENAME)
    if os.path.isfile(default_path):
        return default_path
    return None


def _parse_json(filepath: str) -> dict:
    """Parse a JSON configuration file into a flat dict."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _logger.warning("解析配置文件失败：%s；原因：%s", filepath, e)
        return {}

    if not isinstance(data, dict):
        _logger.warning("配置文件根节点不是对象：%s", filepath)
        return {}

    result: dict = {}
    section_map = {
        ("build", "input"): "input",
        ("build", "template"): "template",
        ("build", "output"): "output",
        ("build", "markdown_engine"): "markdown_engine",
        ("document", "theme"): "theme",
        ("document", "numbering"): "numbering",
        ("features", "copy_assets"): "copy_assets",
        ("features", "build_index"): "build_index",
        ("features", "auto_open"): "auto_open",
        ("features", "overwrite"): "overwrite",
        ("features", "preserve_structure"): "preserve_structure",
        ("features", "verbose"): "verbose",
    }
    for (section, key), flat_key in section_map.items():
        if isinstance(data.get(section), dict) and key in data[section]:
            result[flat_key] = data[section][key]

    # Also accept flat JSON for internal callers or hand-written config.
    for key in _DEFAULTS:
        if key in data:
            result[key] = data[key]

    return result


def load_config(
    config_path: str | None = None,
    cli_overrides: dict | None = None,
) -> dict:
    """Load configuration with priority: CLI > config.json > defaults."""
    cfg = dict(_DEFAULTS)
    path = _find_config(config_path)
    if path:
        _logger.debug("正在加载配置：%s", path)
        file_cfg = _parse_json(path)
        cfg.update(file_cfg)
    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is not None:
                cfg[key] = value
    cfg["template"] = normalize_template_name(cfg.get("template"))
    return cfg


# ================================================================
# Template chain resolution
# ================================================================


def _read_metadata(template_name: str) -> dict:
    """Read metadata.json from a template directory."""
    path = os.path.join(TEMPLATES_DIR, template_name, "metadata.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            _logger.warning("解析模板元数据失败：%s；原因：%s", path, e)
    return {}


def resolve_template_chain(template_name: str) -> list[str]:
    """Build the template inheritance chain.

    Returns list of template names from base to child.
    E.g. for "office" that extends "default": ["default", "office"].

    Raises ValueError if template not found or circular.
    """
    template_name = normalize_template_name(template_name)

    if not os.path.isdir(os.path.join(TEMPLATES_DIR, template_name)):
        raise ValueError(f"未找到模板：“{template_name}”")

    chain = [template_name]
    seen = {template_name}
    current = template_name

    while True:
        meta = _read_metadata(current)
        parent = meta.get("extends")
        if parent is None:
            break
        if parent in seen:
            raise ValueError(
                f"检测到模板循环继承：{' -> '.join(chain + [parent])}"
            )
        if not os.path.isdir(os.path.join(TEMPLATES_DIR, parent)):
            raise ValueError(
                f"模板“{current}”继承“{parent}”，但未找到父模板“{parent}”。"
            )
        chain.insert(0, parent)
        seen.add(parent)
        current = parent

    return chain


def resolve_template_file(template_name: str, filename: str) -> str | None:
    """Find a file in the template chain, starting from child.

    Returns path to the file, or None if not found in any template.
    """
    chain = resolve_template_chain(template_name)
    # Search from child to parent (last in chain first)
    for name in reversed(chain):
        path = os.path.join(TEMPLATES_DIR, name, filename)
        if os.path.isfile(path):
            return path
    return None


def load_theme_chain(template_name: str) -> str:
    """Load and concatenate theme.css files from the inheritance chain.

    Base template's theme.css is loaded first, then each child's theme.css
    is appended. This ensures children override parent variables (CSS cascade).

    Returns concatenated CSS string. Raises ValueError on error.
    """
    chain = resolve_template_chain(template_name)
    parts: list[str] = []
    for name in chain:
        theme_path = os.path.join(TEMPLATES_DIR, name, "theme.css")
        if os.path.isfile(theme_path):
            with open(theme_path, "r", encoding="utf-8") as f:
                parts.append(f.read())
            _logger.debug("已加载模板样式：%s/theme.css", name)
        else:
            _logger.debug("模板 %s 没有 theme.css，已跳过。", name)
    if not parts:
        raise ValueError(
            f"模板“{template_name}”的继承链中没有 theme.css。"
            f"继承链：{' -> '.join(chain)}"
        )
    return "\n".join(parts)


def get_shared_viewer_js_path() -> str:
    """Get path to the shared viewer.js."""
    return _SHARED_VIEWER_JS


def get_shared_print_css_path() -> str:
    """Get path to the shared print.css."""
    return _SHARED_PRINT_CSS


def get_template_paths(template_name: str = "modern") -> dict:
    """Get paths to all template files resolved through inheritance.

    Returns dict with keys: html, css, js, print_css, theme_chain.
    """
    chain = resolve_template_chain(template_name)

    html_path = resolve_template_file(template_name, "viewer.html")
    css_path = resolve_template_file(template_name, "viewer.css")

    return {
        "html": html_path,
        "css": css_path,
        "js": _SHARED_VIEWER_JS,
        "print_css": _SHARED_PRINT_CSS,
        "chain": chain,
    }
