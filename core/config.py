"""MarkdownReader configuration management.

Handles loading config.json and merging it with runtime overrides.

Reader assets -- the page shell, the shared viewer script, the themes and their
inheritance chain -- live in `core/viewer_assets.py`; that layer is the only
place that knows where those files are.
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

# Production renderer policy. This is the single source of truth for what the
# converter uses when no caller asks for a specific renderer, and therefore the
# one line a rollback flips. It is deliberately NOT a config.json value: it is a
# source-level policy, not a user setting (a config model is Phase 8 work).
#
# The renderer_node bridge keeps its own `"v1"` default on purpose -- it is a
# low-level API that can drive either renderer explicitly, not the policy holder.
# Cutover C4 sets this to "v2"; v1 stays available for rollback.
PRODUCTION_RENDERER_VERSION = "v2"

# Template placeholders
PLACEHOLDER_TITLE = "{{TITLE}}"
PLACEHOLDER_TOC = "{{TOC}}"
PLACEHOLDER_CONTENT = "{{CONTENT}}"
# Phase 6C: the document's own default theme is part of the markup, and the theme
# menu ships with the page so it needs no script to be correct.
PLACEHOLDER_THEME_ID = "{{THEME_ID}}"
PLACEHOLDER_THEME_MENU = "{{THEME_MENU}}"

# Default output extension
DEFAULT_OUTPUT_EXTENSION = ".html"

# Runtime configuration file
CONFIG_FILENAME = "config.json"

# Default configuration values
_DEFAULTS: dict = {
    "input": "",
    "template": "modern",
    "output": "output",
    "numbering": False,
    "build_index": True,
    "auto_open": True,
    "overwrite": False,
    "preserve_structure": False,
    "title": None,
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
        ("document", "numbering"): "numbering",
        ("features", "build_index"): "build_index",
        ("features", "auto_open"): "auto_open",
        ("features", "overwrite"): "overwrite",
        ("features", "preserve_structure"): "preserve_structure",
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
    runtime_overrides: dict | None = None,
) -> dict:
    """Load configuration with priority: runtime overrides > config.json > defaults."""
    cfg = dict(_DEFAULTS)
    path = _find_config(config_path)
    if path:
        _logger.debug("正在加载配置：%s", path)
        file_cfg = _parse_json(path)
        cfg.update(file_cfg)
    if runtime_overrides:
        for key, value in runtime_overrides.items():
            if value is not None:
                cfg[key] = value
    cfg["template"] = normalize_template_name(cfg.get("template"))
    return cfg
