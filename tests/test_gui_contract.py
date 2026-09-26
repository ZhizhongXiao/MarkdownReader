import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.app import load_gui_document  # noqa: E402


def test_gui_exposes_multiselect_drop_and_conversion_list_contract():
    html = (ROOT / "gui" / "assets" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "gui" / "assets" / "gui.js").read_text(encoding="utf-8")
    api = (ROOT / "gui" / "api.py").read_text(encoding="utf-8")

    assert 'id="conversion-page"' in html
    assert 'id="tab-conversion"' in html
    assert 'id="drop-overlay"' in html
    assert 'class="input-drop-hint"' in html
    assert 'data-active="preview"' in html
    assert 'class="workspace-tab workspace-tab-log"' in html
    assert 'id="log-issue-count"' in html
    assert "conversion-table-head" not in html
    assert "askopenfilenames" in api
    assert "select_input_files" in javascript
    assert "acceptDroppedInputs" in javascript
    assert '"直接加入"' in javascript
    assert "toggleConversionDetails" in javascript
    assert "appendDetailLine" in javascript
    assert "function updateLogAttention()" in javascript
    assert 'tab.classList.toggle("has-error"' in javascript
    assert 'id="btn-select-files"' in html
    assert 'id="btn-select-dir"' in html
    assert 'id="btn-select-output"' in html
    assert "function setDialogOpen(open)" in javascript
    assert "_one_dialog_at_a_time" in api


def test_template_selection_returns_to_preview_tab():
    javascript = (ROOT / "gui" / "assets" / "gui.js").read_text(encoding="utf-8")
    select_template_body = javascript.split("function selectTemplate(name)", 1)[1].split(
        "function ensureDropdownPortal", 1
    )[0]

    assert "updateTemplatePreview(name)" in select_template_body
    assert "showPreviewTab()" in select_template_body


def test_runtime_gui_document_inlines_current_css_and_javascript():
    document = load_gui_document()

    assert 'id="conversion-page"' in document
    assert ".workspace-tab-log" in document
    assert "function updateLogAttention()" in document
    assert "function acceptDroppedInputs" in document
    assert 'href="gui.css"' not in document
    assert 'src="gui.js"' not in document


def test_native_window_minimum_width_matches_two_column_layout():
    app = (ROOT / "gui" / "app.py").read_text(encoding="utf-8")

    assert '"min_size": (720, 500)' in app


class _StubTk:
    """Minimal stand-in for the hidden root the dialogs create."""

    def withdraw(self):
        return None

    def attributes(self, *_args):
        return None

    def destroy(self):
        return None


def test_a_second_dialog_is_refused_while_one_is_open(monkeypatch):
    """An overlap is what breaks tkinter's process-wide default root.

    pywebview runs every bridge call in a thread of its own, so a second dialog
    can arrive while the first one is still open. The bridge must refuse it
    instead of calling Tcl from the wrong thread.
    """
    import tkinter
    import tkinter.filedialog

    from gui.api import BridgeApi

    monkeypatch.setattr(tkinter, "Tk", _StubTk)
    monkeypatch.setattr(tkinter.filedialog, "askopenfilenames", lambda **_kwargs: ("a.md",))
    monkeypatch.setattr(tkinter.filedialog, "askdirectory", lambda **_kwargs: r"C:\picked")

    api = BridgeApi()
    assert api.select_input_directory() == r"C:\picked"
    assert api.select_input_files() == ["a.md"]

    def must_not_open(**_kwargs):
        raise AssertionError("a second dialog must not reach tkinter")

    monkeypatch.setattr(tkinter.filedialog, "askdirectory", must_not_open)
    monkeypatch.setattr(tkinter.filedialog, "askopenfilenames", must_not_open)

    with api._one_dialog_at_a_time() as opened:
        assert opened is True
        assert api.select_input_directory() == ""
        assert api.select_output_directory() == ""
        assert api.select_input_files() == []

    # The refusal must not leave the lock behind: the next dialog has to work.
    monkeypatch.setattr(tkinter.filedialog, "askdirectory", lambda **_kwargs: r"C:\picked")
    assert api.select_input_directory() == r"C:\picked"


def test_opening_a_result_hands_the_system_a_file_uri(monkeypatch, tmp_path):
    """A bare Windows path is decided by the .html association, not by us.

    A stale association opens something else, or nothing at all; a file:// URI
    says what the target is, and survives spaces and non-ASCII names.
    """
    from gui import api as gui_api

    opened: list[str] = []
    monkeypatch.setattr(gui_api.webbrowser, "open", opened.append)

    target = tmp_path / "索引-示例.html"
    target.write_text("<html><body>ok</body></html>", encoding="utf-8")
    gui_api.BridgeApi().open_file(str(target))

    assert opened == [target.resolve().as_uri()], opened
    assert opened[0].startswith("file:///")

    opened.clear()
    gui_api.BridgeApi().open_file(str(tmp_path / "absent.html"))
    assert opened == [], "a missing file must not be handed to the system"


def test_the_auto_open_path_uses_the_same_file_uri_helper():
    api = (ROOT / "gui" / "api.py").read_text(encoding="utf-8")

    assert "webbrowser.open(_file_uri(entry_file))" in api
    assert "webbrowser.open(_file_uri(path))" in api


def test_gui_exposes_the_external_theme_selection_surface():
    """Phase 9A：主页有自己的外置主题选择面，而不是把选择塞进模板下拉。

    模板下拉是「文档默认主题」，只出 builtin（`get_templates()` 的 docstring 已冻结）；
    外置主题是「本文档额外携带哪些」，两者是不同的概念（AGENTS §17）。
    """
    html = (ROOT / "gui" / "assets" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "gui" / "assets" / "gui.js").read_text(encoding="utf-8")

    assert 'id="external-theme-list"' in html
    assert 'id="external-theme-summary"' in html
    assert 'id="external-theme-empty"' in html
    assert "data-theme-state" in javascript
    assert "data-theme-id" in javascript
    assert "data-theme-action" in javascript
    assert "function renderThemeSelection()" in javascript
    assert "function toggleExternalTheme(" in javascript
    assert "function removeConfiguredTheme(" in javascript
    assert "function saveThemeSelection(" in javascript
    assert "get_theme_state" in javascript


def test_the_runtime_document_carries_the_theme_selection_surface():
    """内联文档必须带上新面：打包/内联路径漏掉它时，窗口会显示一个空壳。"""
    document = load_gui_document()

    assert 'id="external-theme-list"' in document
    assert 'id="external-theme-summary"' in document
    assert "function renderThemeSelection()" in document


def test_the_main_page_selects_themes_and_does_not_manage_them():
    """AGENTS §17：安装 / 删除 / 导出模板 / 打开主题目录属于设置页，主页只管「本次携带哪些」。

    Phase 9A 故意不引入设置入口，设置页整体属于 9B；因此这条守卫同时锁住两件事：
    主页不得出现管理动作，也不得提前出现一个尚无功能的设置按钮。
    """
    html = (ROOT / "gui" / "assets" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "gui" / "assets" / "gui.js").read_text(encoding="utf-8")

    for token in (
        "btn-settings",
        "settings-page",
        "import_theme",
        "remove_theme",
        "export_theme_template",
        "open_theme_location",
    ):
        assert token not in html, token + " belongs to the settings page (phase 9B)"
        assert token not in javascript, token + " belongs to the settings page (phase 9B)"
