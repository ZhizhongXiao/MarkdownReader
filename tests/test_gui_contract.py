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
