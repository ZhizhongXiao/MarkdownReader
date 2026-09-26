"""MarkdownReader configuration management.

Handles loading config.json and merging it with runtime overrides.

Reader assets -- the page shell, the shared viewer script, the themes and their
inheritance chain -- live in `core/viewer_assets.py`; that layer is the only
place that knows where those files are.
"""

import json
import logging
import os
import tempfile

from core import paths

_logger = logging.getLogger(__name__)


def get_bundle_root() -> str:
    """Return the directory containing bundled read-only application assets."""
    return paths.bundle_root()


def get_application_dir() -> str:
    """Return the EXE directory when frozen, otherwise the source root."""
    return paths.application_dir()


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
CONFIG_FILENAME = paths.CONFIG_FILENAME

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
    # Phase 7E: which installed user themes the next documents carry. Builtin themes
    # are bundled into every document and never belong in this list (AGENTS 17).
    "external_themes": [],
}

_TEMPLATE_ALIASES: dict[str, str] = {
    "mordern": "modern",
}


def normalize_template_name(template_name: str | None) -> str:
    """Normalize user-facing template aliases to canonical template ids."""
    name = str(template_name or _DEFAULTS["template"]).strip().lower()
    return _TEMPLATE_ALIASES.get(name, name)


# Only these keys have persistence semantics today. `title` and `overwrite` are runtime
# overrides, so `_DEFAULTS` is deliberately not dumped wholesale: that would turn
# internal policy into user configuration by accident.
_PERSISTED_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("build", ("input", "template", "output", "external_themes")),
    ("document", ("numbering",)),
    ("features", ("build_index", "auto_open", "preserve_structure")),
)

_SECTION_DEFAULTS: dict = {
    "input": "",
    "template": "modern",
    "output": "output",
    "external_themes": [],
    "numbering": False,
    "build_index": True,
    "auto_open": True,
    "preserve_structure": False,
}

# Characters that make an entry look like a path rather than an id. config.json stores
# theme ids; a path would freeze one machine's layout into a portable file.
_PATH_LOOKALIKES = ("/", "\\", ":")


def _clean_external_themes(value, *, strict: bool) -> list[str]:
    """Return the configured user-theme ids, cleaned at the configuration layer only.

    It never asks whether a theme is installed: a theme that is temporarily missing must
    not erase the user's choice (AGENTS section 17). ``strict`` is for values the program
    passes to `save_config` -- a path-like id there is a caller bug, not a typo in
    somebody's JSON, so it raises instead of being dropped.
    """
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        if strict:
            raise ValueError(f"external_themes 必须是列表：{value!r}")
        _logger.warning("忽略无效的 external_themes（不是列表）：%r", value)
        return []

    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            if strict:
                raise ValueError(f"external_themes 只接受字符串：{item!r}")
            _logger.warning("忽略无效的外置主题条目（不是字符串）：%r", item)
            continue
        theme_id = item.strip()
        if not theme_id:
            continue
        if any(marker in theme_id for marker in _PATH_LOOKALIKES):
            if strict:
                raise ValueError(f"external_themes 只接受主题 ID，不接受路径：{theme_id}")
            _logger.warning("忽略疑似路径的外置主题条目：%s", theme_id)
            continue
        if theme_id in cleaned:
            continue
        cleaned.append(theme_id)
    return cleaned


def normalize_config(cfg: dict, *, strict: bool = False) -> dict:
    """Return a configuration dict with the theme fields normalized.

    `template` keeps using this module's own `normalize_template_name()`: config owns the
    selector syntax, and importing the asset layer here would reverse the dependency
    direction (viewer_assets already depends on config).
    """
    normalized = dict(cfg)
    normalized["template"] = normalize_template_name(normalized.get("template"))
    normalized["external_themes"] = _clean_external_themes(
        normalized.get("external_themes"), strict=strict
    )
    return normalized


def _to_sections(cfg: dict) -> dict:
    """Return the canonical sectioned JSON shape written to a config file."""
    sections: dict = {}
    for section, keys in _PERSISTED_SECTIONS:
        sections[section] = {key: cfg.get(key, _SECTION_DEFAULTS[key]) for key in keys}
    return sections


def save_config(cfg: dict, config_path: str | None = None) -> str:
    """Persist the configuration atomically and return the path written.

    Writes to `profile/config.json` (Phase 8B): the EXE directory may be read-only, and
    the profile location is where the rest of the user data will live. The temporary file
    is created beside the target so `os.replace` stays on one volume, and a failure
    leaves the previous file byte for byte as it was.
    """
    data = _to_sections(normalize_config(cfg, strict=True))
    path = str(config_path) if config_path else paths.config_path()
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    handle, temp_path = tempfile.mkstemp(prefix=CONFIG_FILENAME + ".tmp-", dir=directory)
    os.close(handle)
    try:
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    _logger.info("配置已保存：%s", path)
    return path


def _find_config(config_path: str | None = None) -> str | None:
    """Return the configuration file to read.

    Order: an explicit path, then `profile/config.json`, then the legacy file beside the
    application, then nothing (defaults). The profile file wins *even when it is
    unreadable*: from Phase 8B on it is the real file, and falling back to the legacy copy
    would make an old file reappear whenever the new one is damaged.
    """
    if config_path and os.path.isfile(config_path):
        return config_path
    profile_path = paths.config_path()
    if os.path.isfile(profile_path):
        return profile_path
    legacy_path = os.path.join(PROJECT_ROOT, CONFIG_FILENAME)
    if os.path.isfile(legacy_path):
        return legacy_path
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
        ("build", "external_themes"): "external_themes",
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
    cfg["external_themes"] = _clean_external_themes(cfg.get("external_themes"), strict=False)
    return cfg
