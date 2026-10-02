"""External-theme bridge operations, kept separate from the carry-selection facade."""

import logging
import os
from collections.abc import Callable

from core.config import load_config
from core.external_themes import (
    ensure_theme_root,
    export_template,
    theme_inventory,
    theme_state,
)
from core.external_themes import import_theme as install_theme
from core.external_themes import remove_theme as uninstall_theme
from gui.services.dialogs import DialogInputService

_logger = logging.getLogger("gui")
EXPORTED_TEMPLATE_DIR_NAME = "markdownreader-theme-template"


def _refused_theme() -> dict:
    return {"ok": False, "id": "", "error": "移除用户数据已开始，本次操作被拒绝。"}


def _refused_path() -> dict:
    return {"ok": False, "path": "", "error": "移除用户数据已开始，本次操作被拒绝。"}


class ThemeService:
    """Implement installed-theme facts and management operations for settings."""

    def __init__(
        self,
        dialogs: DialogInputService,
        open_directory: Callable[[str], None],
    ) -> None:
        self._dialogs = dialogs
        self._open_directory = open_directory

    def get_theme_state(self) -> dict:
        """Return remembered, selectable, missing, unusable, and preview theme facts."""
        cfg = load_config()
        configured = list(cfg.get("external_themes") or [])
        state = theme_state(configured)
        return {
            "installed": state["installed"],
            "configured": configured,
            "selected": state["selected"],
            "missing": state["missing"],
            "invalid": state["invalid"],
            "installed_invalid": state["installed_invalid"],
            "previews": state["previews"],
            "warnings": state["warnings"],
        }

    def get_theme_inventory(self) -> dict:
        """Return every installed user theme with its own validity verdict."""
        return theme_inventory()

    def import_theme(self, request: dict | None = None) -> dict:
        """Install a theme, asking for its directory if the request has no source."""
        request = request or {}
        source = str(request.get("source") or "")
        if not source:
            picked = self._dialogs.choose_directory("选择要导入的主题目录")
            if picked is None:
                return {"ok": False, "id": "", "error": "已有对话框打开，请稍后再试。"}
            source = picked
            if not source:
                return {"ok": False, "id": "", "error": "未选择任何目录。"}
        try:
            theme_id = install_theme(source, replace=bool(request.get("replace", False)))
        except Exception as error:
            _logger.warning("导入外置主题失败：%s", error)
            return {"ok": False, "id": "", "error": str(error)}
        return {"ok": True, "id": theme_id, "error": ""}

    def remove_theme(self, theme_id: str) -> dict:
        """Delete only the installed theme copy; the saved carry selection remains untouched."""
        try:
            uninstall_theme(theme_id)
        except Exception as error:
            _logger.warning("卸载外置主题失败：%s", error)
            return {"ok": False, "id": str(theme_id), "error": str(error)}
        return {"ok": True, "id": str(theme_id), "error": ""}

    def export_theme_template(self, request: dict | None = None) -> dict:
        """Copy the packaged theme template into a folder the user picks."""
        request = request or {}
        destination = str(request.get("destination") or "")
        if not destination:
            picked = self._dialogs.choose_directory("选择导出主题模板的位置")
            if picked is None:
                return {"ok": False, "path": "", "error": "已有对话框打开，请稍后再试。"}
            if not picked:
                return {"ok": False, "path": "", "error": "未选择任何目录。"}
            destination = os.path.join(picked, EXPORTED_TEMPLATE_DIR_NAME)
        try:
            path = export_template(destination)
        except Exception as error:
            _logger.warning("导出主题模板失败：%s", error)
            return {"ok": False, "path": "", "error": str(error)}
        return {"ok": True, "path": path, "error": ""}

    def open_theme_location(self) -> dict:
        """Create the external theme directory if missing, then reveal it."""
        try:
            root = ensure_theme_root()
            self._open_directory(root)
        except Exception as error:
            _logger.warning("打开外置主题目录失败：%s", error)
            return {"ok": False, "path": "", "error": str(error)}
        return {"ok": True, "path": root, "error": ""}
