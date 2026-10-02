// ── Theme preview (Phase 12 GUI closeout) ──────────────────────────────────────
//
// The right-hand stage answers "what does this theme look like" before any document exists. It is
// a session view: switching the preview changes the stage and nothing else. A builtin theme is
// switched by class, an external theme's six declarative tokens arrive as CSS variables on the
// stage -- the GUI never runs user CSS -- and a theme whose preview metadata is missing or broken
// degrades to a notice, because it is still a theme this document may carry and convert.

var PREVIEW_CLASSES = ["preview-modern", "preview-office", "preview-vscode", "preview-external"];
var PREVIEW_TOKENS = ["background", "surface", "text", "muted", "accent", "border"];

function previewFacts(id) {
    var facts = _themePreviews ? _themePreviews[id] : null;
    return facts && typeof facts === "object" ? facts : null;
}

function isBuiltinTheme(id) { return BUILTIN_THEMES.indexOf(id) !== -1; }

function selectPreviewTheme(id) {
    if (!id) return;
    _previewTheme = id;
    renderThemePreview();
}

// External preview targets: the installed, usable themes the bridge reported preview facts for.
// An unusable installation is not a preview target, and neither is an id without facts.
function previewTargetIds() {
    var state = _themeState || {};
    var unusable = (state.invalid || []).concat(state.installed_invalid || []);
    var ids = [];
    (state.installed || []).forEach(function (id) {
        if (ids.indexOf(id) === -1 && unusable.indexOf(id) === -1 && previewFacts(id)) ids.push(id);
    });
    return ids;
}

function previewTargetAvailable(id) {
    if (isBuiltinTheme(id)) return true;
    return !!previewFacts(id) && previewTargetIds().indexOf(id) !== -1;
}

function previewableThemeIds() {
    var ids = BUILTIN_THEMES.slice();
    previewTargetIds().forEach(function (id) {
        if (ids.indexOf(id) === -1) ids.push(id);
    });
    return ids;
}

function previewThemeName(id) {
    var builtinNames = { modern: "Modern", office: "Office", vscode: "VS Code" };
    if (builtinNames[id]) return builtinNames[id];
    var facts = previewFacts(id);
    return (facts && facts.name) || id;
}

function renderPreviewNav() {
    var name = document.getElementById("preview-theme-name");
    if (name) {
        name.textContent = previewThemeName(_previewTheme);
        var facts = previewFacts(_previewTheme);
        name.title = (facts && facts.description) || _previewTheme;
    }
    renderPreviewMarks();
}

function stepPreviewTheme(direction) {
    var ids = previewableThemeIds();
    if (ids.length < 2) return;
    var index = ids.indexOf(_previewTheme);
    if (index < 0) index = direction > 0 ? -1 : 0;
    var nextIndex = (index + direction + ids.length) % ids.length;
    selectPreviewTheme(ids[nextIndex]);
}

function bindPreviewNav() {
    var previous = document.getElementById("btn-preview-prev");
    var next = document.getElementById("btn-preview-next");
    if (previous) previous.addEventListener("click", function () { stepPreviewTheme(-1); });
    if (next) next.addEventListener("click", function () { stepPreviewTheme(1); });
}

// Both marks come from `_previewTheme` alone. The carry checkbox never feeds them, so a carried
// theme and the previewed theme stay visibly separate: a row can be checked without being shown,
// and the preview never changes what a document carries.
function renderPreviewMarks() {
    var rows = document.querySelectorAll(".theme-row[data-theme-id]");
    for (var i = 0; i < rows.length; i += 1) {
        var rowId = rows[i].getAttribute("data-theme-id");
        rows[i].classList.toggle("previewing", rowId === _previewTheme);
    }
}

function renderThemePreview() {
    var notice = previewNotice(_previewTheme);
    var stage = document.getElementById("theme-preview");
    if (stage) {
        var facts = previewFacts(_previewTheme);
        var tokens = facts && facts.preview ? facts.preview : null;
        stage.classList.toggle("hidden", !!notice);
        PREVIEW_CLASSES.forEach(function (name) { stage.classList.remove(name); });
        stage.classList.add(
            isBuiltinTheme(_previewTheme) ? "preview-" + _previewTheme : "preview-external"
        );
        stage.setAttribute("data-preview-theme", _previewTheme);
        PREVIEW_TOKENS.forEach(function (token) {
            if (tokens) {
                stage.style.setProperty("--preview-" + token, String(tokens[token]));
            } else {
                stage.style.removeProperty("--preview-" + token);
            }
        });
    }

    var fallback = document.getElementById("preview-fallback");
    if (fallback) {
        fallback.classList.toggle("hidden", !notice);
        var reason = document.getElementById("preview-fallback-reason");
        if (notice && reason) reason.textContent = notice;
        if (!notice && reason) reason.textContent = "";
    }
    renderPreviewNav();
}

// A missing or malformed preview is a GUI inconvenience, never a broken theme: the theme still
// converts, it simply has no palette to show, so this reads as a notice instead of an error.
function previewNotice(id) {
    if (isBuiltinTheme(id)) return "";
    var facts = previewFacts(id);
    var status = facts ? String(facts.preview_status || "missing") : "missing";
    if (status === "available") return "";
    if (status === "invalid") {
        var reason = facts ? String(facts.preview_reason || "") : "";
        return "预览配色不合法" + (reason ? "（" + reason + "）" : "") + "；主题本身仍然可用。";
    }
    return "主题可以照常携带与转换，这里只显示默认外观。";
}
