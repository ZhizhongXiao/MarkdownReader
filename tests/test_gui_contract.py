from pathlib import Path

from gui.app import load_gui_document

ROOT = Path(__file__).resolve().parents[1]


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
