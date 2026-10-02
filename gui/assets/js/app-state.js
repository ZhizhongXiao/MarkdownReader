// Application state
var _lastOutputDir = "output";
var _lastOutputFile = "";
var _themeMode = "auto";
// Phase 12 GUI closeout: the builtin conversion selector is gone. A builtin theme is a reader
// preference now (the reader keeps the last one per document), so this page owns only the
// *preview* state below -- and the theme a document falls back to is a bridge-side constant.
var BOOTSTRAP_THEME = "modern";
var BUILTIN_THEMES = ["modern", "office", "vscode"];
var _inputSources = [];
var _conversionItems = [];
var _planWarnings = [];
var _planErrors = [];
var _planRevision = 0;
var _apiReady = false;
// The log keeps its history, so the history needs a bound.
var LOG_CAPACITY = 500;
var _conversionRunning = false;
// A native dialog is a modal, single-owner resource: while one is open every
// other dialog control is disabled, so a second call cannot overlap it.
var _dialogOpen = false;
var _expandedItems = {};
var _logIssueCount = 0;
var _logIssueLevel = "";
// The external theme surface (phase 9A). `_themeState` is the bridge's answer and
// `_themeSelection` is what the next document will carry: it starts as a copy of the
// configured list, so a theme that is merely gone stays remembered until the user
// drops it. `_themeSavePending` is the newest unconfirmed selection and
// `_themeSaveInFlight` makes the writes serial, so an older payload can never land
// after a newer one.
var _themeState = null;
var _themeSelection = [];
var _themeSaveInFlight = false;
var _themeSavePending = null;
// The promise of the write currently draining. A run awaits it instead of guessing, and
// its value is what the run gates on: "the queue stopped" is not "the selection is in
// the file".
var _themeSaveDrain = null;
// The last selection known to be persisted. A failed write falls back to this, never to
// the startup snapshot: a save may already have succeeded since the page loaded.
var _themeConfirmed = [];
// The preview state (Phase 12 GUI closeout). `_themePreviews` is the bridge's preview facts,
// keyed by theme id; `_previewTheme` is what the right-hand stage shows. The preview belongs to
// this session: it changes the stage and nothing else -- no configuration write, and no reader
// preference, because the reader owns that.
var _previewTheme = BOOTSTRAP_THEME;
var _themePreviews = {};

function pathKey(value) {
    return String(value || "").replace(/\\/g, "/").toLowerCase();
}

function basename(value) {
    var parts = String(value || "").replace(/\\/g, "/").split("/");
    return parts[parts.length - 1] || value;
}
