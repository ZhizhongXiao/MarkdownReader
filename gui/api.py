"""Stable pywebview bridge facade for the GUI's JavaScript context."""

from collections.abc import Iterator
from contextlib import contextmanager

from core.conversion_plan import ConversionPlan
from gui.services.conversion import ConversionResult, ConversionService, _refused_plan
from gui.services.dialogs import DialogInputService
from gui.services.lifecycle import LifecycleStorageService, WebViewWindow
from gui.services.themes import ThemeService

# The generated reader uses this builtin theme only when no reader-side preference exists.
# The GUI has no builtin theme selector; requests cannot override this boundary default.
BOOTSTRAP_TEMPLATE = "modern"


def _refused_theme() -> dict:
    return {"ok": False, "id": "", "error": "移除用户数据已开始，本次操作被拒绝。"}


def _refused_path() -> dict:
    return {"ok": False, "path": "", "error": "移除用户数据已开始，本次操作被拒绝。"}


class BridgeApi:
    """Public API exposed to pywebview; service details stay behind this facade."""

    def __init__(self) -> None:
        self._lifecycle = LifecycleStorageService()
        self._dialogs = DialogInputService()
        self._themes = ThemeService(self._dialogs, self._lifecycle.open_directory)
        self._conversion = ConversionService(
            self._lifecycle.notify_conversion_status,
            self._lifecycle.open_file_uri,
            BOOTSTRAP_TEMPLATE,
        )

    @contextmanager
    def _operation(self) -> Iterator[bool]:
        """Route each bridge operation through the single terminal-removal gate."""
        with self._lifecycle.operation() as allowed:
            yield allowed

    @contextmanager
    def _one_dialog_at_a_time(self) -> Iterator[bool]:
        """Keep the existing dialog serialization seam for callers and tests."""
        with self._dialogs.one_dialog_at_a_time() as opened:
            yield opened

    def attach_window(self, window: WebViewWindow) -> None:
        """Attach the created webview window for progress and shutdown events."""
        self._lifecycle.attach_window(window)

    def _notify_conversion_status(
        self,
        source_path: str,
        status: str,
        warnings: list[str] | None = None,
        output_path: str = "",
    ) -> None:
        self._lifecycle.notify_conversion_status(source_path, status, warnings, output_path)

    # Native file and directory inputs

    def select_input_files(self) -> list[str]:
        with self._operation() as allowed:
            return self._dialogs.select_input_files() if allowed else []

    def select_input_directory(self) -> str:
        with self._operation() as allowed:
            return self._dialogs.select_input_directory() if allowed else ""

    def select_output_directory(self) -> str:
        with self._operation() as allowed:
            return self._dialogs.select_output_directory() if allowed else ""

    def prepare_conversion(self, request: dict | None = None) -> ConversionPlan:
        with self._operation() as allowed:
            return self._conversion.prepare(request) if allowed else _refused_plan()

    # Profile and theme state

    def get_config(self) -> dict:
        with self._operation() as allowed:
            return self._lifecycle.get_config() if allowed else {}

    def set_configs(self, overrides: dict) -> None:
        with self._operation() as allowed:
            if allowed:
                self._lifecycle.set_configs(overrides)

    def get_theme_state(self) -> dict:
        with self._operation() as allowed:
            return self._themes.get_theme_state() if allowed else {}

    # Theme installation and maintenance

    def get_theme_inventory(self) -> dict:
        with self._operation() as allowed:
            return self._themes.get_theme_inventory() if allowed else {}

    def import_theme(self, request: dict | None = None) -> dict:
        with self._operation() as allowed:
            return self._themes.import_theme(request) if allowed else _refused_theme()

    def remove_theme(self, theme_id: str) -> dict:
        with self._operation() as allowed:
            return self._themes.remove_theme(theme_id) if allowed else _refused_theme()

    def export_theme_template(self, request: dict | None = None) -> dict:
        with self._operation() as allowed:
            return self._themes.export_theme_template(request) if allowed else _refused_path()

    def open_theme_location(self) -> dict:
        with self._operation() as allowed:
            return self._themes.open_theme_location() if allowed else _refused_path()

    # Storage and application facts

    def get_storage_info(self) -> dict:
        return self._lifecycle.get_storage_info()

    def get_about_info(self) -> dict:
        return self._lifecycle.get_about_info()

    # Conversion

    def convert(self, request: dict | None = None) -> ConversionResult:
        with self._operation() as allowed:
            if not allowed:
                return {"success": False, "files": [], "errors": [
                    "移除用户数据已开始，本次操作被拒绝。"
                ]}
            return self._convert(request)

    def _convert(self, request: dict | None = None) -> ConversionResult:
        """Internal conversion seam retained so the facade owns the removal gate."""
        return self._conversion.convert(request)

    # System integration

    def open_file(self, path: str) -> None:
        self._lifecycle.open_file(path)

    def open_directory(self, path: str) -> None:
        self._lifecycle.open_directory(path)

    # Terminal removal

    def request_user_data_removal(self) -> dict:
        return self._lifecycle.request_user_data_removal()

    def _destroy_window(self) -> bool:
        return self._lifecycle._destroy_window()

    def _should_remove_user_data_on_exit(self) -> bool:
        return self._lifecycle.should_remove_user_data_on_exit()
