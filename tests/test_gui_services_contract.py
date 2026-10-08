"""The GUI bridge stays stable while its Python implementation is service-based."""

import inspect
import re
from pathlib import Path

from gui.api import BridgeApi
from gui.app import load_gui_javascript
from gui.services.conversion import ConversionService
from gui.services.dialogs import DialogInputService
from gui.services.lifecycle import LifecycleStorageService
from gui.services.themes import ThemeService

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_PARAMETERS = {
    "attach_window": ["self", "window"],
    "select_input_files": ["self"],
    "select_input_directory": ["self"],
    "select_output_directory": ["self"],
    "prepare_conversion": ["self", "request"],
    "get_backend_status": ["self"],
    "get_config": ["self"],
    "set_configs": ["self", "overrides"],
    "get_theme_state": ["self"],
    "get_theme_inventory": ["self"],
    "import_theme": ["self", "request"],
    "remove_theme": ["self", "theme_id"],
    "export_theme_template": ["self", "request"],
    "open_theme_location": ["self"],
    "get_storage_info": ["self"],
    "get_about_info": ["self"],
    "convert": ["self", "request"],
    "open_file": ["self", "path"],
    "open_directory": ["self", "path"],
    "request_user_data_removal": ["self"],
}


def test_bridge_keeps_its_complete_public_method_and_parameter_surface():
    public_methods = {
        name
        for name, method in inspect.getmembers(BridgeApi, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods == set(EXPECTED_PARAMETERS)
    for name, expected in EXPECTED_PARAMETERS.items():
        parameters = list(inspect.signature(getattr(BridgeApi, name)).parameters)
        assert parameters == expected, name

    javascript = load_gui_javascript()
    bridge_calls = set(re.findall(r"pywebview\.api\.([A-Za-z_]\w*)", javascript))
    assert bridge_calls <= public_methods


def test_bridge_facade_composes_the_four_backend_services():
    bridge = BridgeApi()

    assert isinstance(bridge._dialogs, DialogInputService)
    assert isinstance(bridge._conversion, ConversionService)
    assert isinstance(bridge._themes, ThemeService)
    assert isinstance(bridge._lifecycle, LifecycleStorageService)
