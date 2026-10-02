import re
import sys
from html.parser import HTMLParser
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


def test_the_page_has_no_builtin_theme_selector():
    """Phase 12 GUI closeout: the builtin "template" control left the product.

    A builtin theme is a reader preference -- the reader keeps the last one per document
    (`viewer/js/theme-switcher.js`) -- so the GUI has no builtin conversion selector. What
    remains is a preview navigation that only changes what the static stage shows, and the
    external theme rows that decide what a document carries.
    """
    html = (ROOT / "gui" / "assets" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "gui" / "assets" / "gui.js").read_text(encoding="utf-8")

    assert "template-select" not in html, "the retired builtin selector must not come back"
    assert "template-select" not in javascript
    assert "buildTemplateDropdown" not in javascript
    assert "selectTemplate" not in javascript
    assert "get_templates" not in javascript
    assert "function selectPreviewTheme(" in javascript
    assert "function showPreviewTab()" in javascript


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
    """Phase 9A: the main page has its own external-theme surface.

    Phase 12 GUI closeout sharpened the vocabulary the docstring used to carry: there is no
    builtin selector at all (a builtin theme is a reader preference), while an external theme has
    a carry state -- "does this document embed it" -- and that is what this surface drives
    (AGENTS §17).
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


def test_the_settings_surface_exists_and_the_main_page_still_does_not_manage_themes():
    """AGENTS §17：安装 / 删除 / 导出模板 / 打开主题目录属于设置页，主页只管「本次携带哪些」。

    Phase 9A 冻结了这条边界（当时整条反向断言：设置面必须不存在）。Phase 9B1 落地设置面
    之后，守卫锁的仍是同一件事，只是换成正面 + 体抽取：设置面必须存在，而主页的主题渲染
    函数里不得出现任何管理动作 —— 主页读到的是「携带集合」，不是「安装清单」。
    """
    html = (ROOT / "gui" / "assets" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "gui" / "assets" / "gui.js").read_text(encoding="utf-8")

    assert 'id="btn-settings"' in html
    assert 'id="settings-page"' in html
    assert "function renderThemeSelection()" in javascript

    management = ("import_theme", "remove_theme", "export_theme_template", "open_theme_location")
    for token in management:
        assert token in javascript, token + " is the settings page's own bridge call"

    renderer = javascript.split("function renderThemeSelection()", 1)[1].split(
        "\nfunction applyThemeControlLock", 1
    )[0]
    for token in management:
        assert token not in renderer, (
            token + " must not run from the main page: installing a theme is not selecting it"
        )

    assert 'data-active="settings"' not in html, "the settings page is not a workspace tab"


def test_removing_user_data_is_promised_only_behind_the_onefile_fact():
    """Phase 11 取代 9B 的反向守卫：动作必须真的存在，但按责任分层、且不越过 backend 事实。

    9B 锁的是「还不许承诺」；Phase 10 把 storage ownership 收口之后，这条契约改写成「承诺必须
    完整」——HTML 只负责入口与弹窗的 DOM 身份，JS 只负责倒计时与发一次请求，Python 才是终止
    状态的 owner，而删文件只发生在 `webview.start()` 返回之后。
    """
    html = (ROOT / "gui" / "assets" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "gui" / "assets" / "gui.js").read_text(encoding="utf-8")
    api = (ROOT / "gui" / "api.py").read_text(encoding="utf-8")

    for token in (
        'id="btn-remove-user-data"',
        'id="user-data-confirm"',
        'id="user-data-countdown"',
        'id="btn-user-data-confirm"',
        'id="btn-user-data-cancel"',
    ):
        assert token in html, token + " must exist in index.html"

    assert "request_user_data_removal" in javascript, "the page asks instead of deleting"
    assert "user-data-countdown" in javascript
    assert "removal_available" in javascript, "the entry follows the backend fact"
    assert "sys.frozen" not in javascript, "the page must not guess the packaging mode"
    assert "LOCALAPPDATA" not in javascript

    assert "request_user_data_removal" in api
    assert "shutil.rmtree" not in api, "the bridge must not delete files itself"


def test_the_theme_closeout_surfaces_are_in_place():
    """Phase 12 GUI closeout: the new vocabulary exists, and the reader keeps its own state.

    The preview navigation, the row anatomy and the settings disclosure are the surfaces the GUI
    contracts drive; this guard keeps them from disappearing while the behaviour tests stay green
    for other reasons.
    """
    html = (ROOT / "gui" / "assets" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "gui" / "assets" / "gui.css").read_text(encoding="utf-8")
    javascript = (ROOT / "gui" / "assets" / "gui.js").read_text(encoding="utf-8")

    assert 'id="theme-preview"' in html, "the static preview stage"
    assert html.count('class="theme-icon theme-icon-moon"') == 1
    assert html.count('class="theme-icon theme-icon-sun"') == 1
    assert "☾" not in html and "☼" not in html, "fixed SVG boxes prevent glyph-width shifts"
    assert 'html[data-theme="dark"] .theme-btn .theme-icon-sun { display: block; }' in css
    assert 'id="btn-preview-prev"' in html
    assert 'id="btn-preview-next"' in html
    assert 'aria-label="上一个主题预览"' in html
    assert 'aria-label="下一个主题预览"' in html
    assert 'id="btn-random-preview"' not in html
    assert 'id="preview-fallback"' in html, "a theme without preview metadata needs its notice"
    assert re.search(r"<details[^>]*id=\"settings-storage-details\"", html), (
        "the detailed storage paths belong behind a native disclosure"
    )
    assert "theme-row-check" in javascript
    assert "theme-row-name" in javascript
    assert "theme-row-desc" in javascript
    assert "markdownreader-theme-id" not in javascript, (
        "the reader owns its preference: the GUI must not write it"
    )
    assert html.count('<header class="header">') == 1, "both views reuse one title bar"
    assert "settings-head" not in html
    assert '<h1>MarkdownReader</h1>' in html
    assert html.count("Markdown 到离线 HTML 阅读器") == 1
    assert 'class="theme-btn settings-view-toggle" id="btn-settings"' in html
    assert 'id="themeToggleBtnSettings"' not in html
    assert "function setSettingsView(isOpen)" in javascript
    assert "function toggleSettings()" in javascript
    assert 'title = isOpen ? "返回主页面" : "设置"' in javascript
    assert 'aria-label", isOpen ? "返回主页面" : "打开设置"' in javascript
    assert re.search(r"\.theme-btn\s*\{[^}]*width:\s*36px[^}]*height:\s*32px", css)
    assert 'class="settings-return-icon"' in html
    assert 'transform="translate(0 1.5)"' in html
    assert (
        ".app.settings-open .settings-view-toggle .settings-return-icon { display: block; }"
        in css
    )
    assert html.index("settings-block-primary") < html.index("settings-block-storage")
    assert html.index("settings-block-storage") < html.index("settings-block-about")
    assert html.index("settings-block-about") < html.index("settings-block-danger")
    assert re.search(r"\.settings-body\s*\{[^}]*width:\s*100%", css)
    assert re.search(r"\.settings-body\s*\{[^}]*align-items:\s*stretch", css)
    assert re.search(
        r"\.settings-block-primary\s*\{[^}]*grid-column:\s*1\s*;\s*grid-row:\s*1\s*/\s*span\s*3",
        css,
    )
    assert "max-width: 1160px" not in css, "settings uses the same page width as the main surface"
    assert re.search(r"\.settings-actions button\s*\{[^}]*min-width:\s*180px", css)
    assert ".settings-block-danger { border-left: 4px solid var(--red); }" in css
    assert re.search(r'<details[^>]*id="settings-storage-details"[^>]*\bopen(?:\s|>)', html)


def test_the_previewing_mark_comes_from_the_preview_id():
    """Phase 12 GUI closeout: the marked row is the previewed one, never the carried one.

    The behaviour contract (GP10) proves the two states stay independent while carry changes;
    this one keeps the implementation honest about where the mark comes from.
    """
    javascript = (ROOT / "gui" / "assets" / "gui.js").read_text(encoding="utf-8")
    marked = [line.strip() for line in javascript.splitlines() if "previewing" in line]

    assert marked, "the previewed row must be marked"
    assert all("_previewTheme" in line for line in marked), (
        "the previewing mark must derive from the preview id (_previewTheme), not from carry: "
        + " | ".join(marked)
    )

    assert "rmtree" not in javascript, "and neither may the page"


# ── 结构守卫（Phase 12 人工验收发现的回归） ─────────────────────
#
# 2026-09-30 两次人工验收各撞出一个「标签配平、但嵌套错」的回归：
#   ① index.html 多一个 `</div>` → `.left-column` 提前闭合：左栏只剩一段、「外置主题」/「选项」掉到
#      `.left-wrapper`下，`.workspace-panel` 直接落到 `body`（两栏搁成上下两行）；
#   ② fallback 块替换掉了 `#preview-page` 的收尾 `</div>` → `#log-page` 成为它的子节点，
#      日志页永远显示不出来。
# 当时所有守卫都是字符串级的（类名与文案是否存在），没有一条问「谁是谁的孩子」，
# 所以两个形状都漏了过去。下面按**整页顶层映射**断言：每个容器必须拥有它应有的直接子节点。

VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
     "source", "track", "wbr"}
)


class _ElementParser(HTMLParser):
    """Record every element with its parent, the way a browser nests them."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list = []
        self.stack: list = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.elements.append({
            "tag": tag,
            "id": attributes.get("id") or "",
            "classes": (attributes.get("class") or "").split(),
            "parent": self.stack[-1] if self.stack else None,
        })
        if tag not in VOID_ELEMENTS:
            self.stack.append(len(self.elements) - 1)

    def handle_endtag(self, tag):
        for position in range(len(self.stack) - 1, -1, -1):
            if self.elements[self.stack[position]]["tag"] == tag:
                del self.stack[position:]
                return


def _elements(markup: str) -> list:
    parser = _ElementParser()
    parser.feed(markup)
    return parser.elements


def _describe(node: dict) -> str:
    label = node["tag"]
    if node["id"]:
        label += "#" + node["id"]
    if node["classes"]:
        label += "." + ".".join(node["classes"])
    return label


def _children(elements: list, index: int) -> list:
    return [node for node in elements if node["parent"] == index]


def _first(elements: list, *, classes: tuple = (), element_id: str = "") -> int:
    for index, node in enumerate(elements):
        if element_id and node["id"] != element_id:
            continue
        if classes and not set(classes) <= set(node["classes"]):
            continue
        return index
    raise AssertionError("element not found: " + (("#" + element_id) if element_id else
    ".".join(classes)))


def _chain(elements: list, index: int) -> list:
    chain = []
    parent = elements[index]["parent"]
    while parent is not None:
        chain.append(elements[parent])
        parent = elements[parent]["parent"]
    return chain


def test_the_page_keeps_its_structural_map():
    """整页顶层映射：每个容器必须直接拥有它应有的子节点。

    这一条抓的是「标签配平 ≠ 嵌套正确」：两次回归都是 div 总数平的，
    但容器关系已经错了。
    """
    markup = (ROOT / "gui" / "assets" / "index.html").read_text(encoding="utf-8")
    elements = _elements(markup)

    app = _first(elements, classes=("app",))
    assert [_describe(node) for node in _children(elements, app)] == [
        "header.header",
        "section.status-strip",
        "main.main",
        "div#settings-page.settings-page.hidden",
    ], "`.app` 必须只直接拥有 header / status-strip / main / settings-page"

    main = _first(elements, classes=("main",))
    assert [_describe(node) for node in _children(elements, main)] == [
        "div.left-wrapper",
        "section.workspace-panel",
    ], "两栏布局必须仍是 <main> 的两个直接子节点"

    left_column = _first(elements, classes=("left-column",))
    left_children = _children(elements, left_column)
    assert [_describe(node) for node in left_children] == ["details.accordion"] * 3, (
        "左栏必须直接拥有三段（文件与输出 / 外置主题 / 选项），实际 "
        + str([_describe(node) for node in left_children])
    )

    panel = _first(elements, classes=("workspace-panel",))
    assert [_describe(node) for node in _children(elements, panel)] == [
        "div#workspace-tabs.workspace-tabs",
        "div#conversion-page.workspace-page.conversion-page",
        "div#preview-page.workspace-page.preview-page.active",
        "div#log-page.workspace-page.log-page",
    ], "右侧工作区必须是 tabs + 三个页的平级结构"

    body_index = next(
        index for index, node in enumerate(elements) if node["tag"] == "body"
    )
    body_children = _children(elements, body_index)
    body_ids = [node["id"] for node in body_children]
    assert _describe(body_children[0]) == "div.app"
    for element_id in ("user-data-confirm", "drop-overlay"):
        assert element_id in body_ids, (
            "#" + element_id + " 必须是 body 的直接子节点，实际："
            + str([_describe(node) for node in body_children])
        )

    for element_id in ("external-theme-list", "chk-auto-open", "chk-build-index"):
        node = _first(elements, element_id=element_id)
        assert any("left-column" in ancestor["classes"] for ancestor in _chain(elements, node)), (
            "#" + element_id + " 必须仍在 .left-column 里"
        )

    log_area = _first(elements, element_id="log-area")
    assert any(ancestor["id"] == "log-page" for ancestor in _chain(elements, log_area)), (
        "#log-area 必须在 #log-page 里（日志页不得被套进预览页）"
    )
