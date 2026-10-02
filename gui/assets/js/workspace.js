// Log helpers
function updateLogAttention() {
    var tab = document.getElementById("tab-log");
    var icon = document.getElementById("log-alert-icon");
    var count = document.getElementById("log-issue-count");
    if (!tab || !icon || !count) return;

    var hasIssues = _logIssueCount > 0;
    tab.classList.toggle("has-warning", hasIssues && _logIssueLevel === "warning");
    tab.classList.toggle("has-error", hasIssues && _logIssueLevel === "error");
    icon.classList.toggle("hidden", !hasIssues);
    count.classList.toggle("hidden", !hasIssues);
    icon.textContent = _logIssueLevel === "error" ? "×" : "!";
    count.textContent = _logIssueCount;
    // The badge counts this round only, so the label must say so: the log
    // itself keeps its history and is therefore larger than this number.
    tab.setAttribute("aria-label", hasIssues ? "日志，本轮 " + _logIssueCount + " 个问题" : "日志");
}

// The lock is state, not just disabled controls: dropping files or calling a
// mutator directly must not change the inputs of a run that is already in flight.
function setConversionRunning(running) {
    _conversionRunning = running;
    var runButton = document.querySelector(".btn-run");
    if (runButton) runButton.disabled = running;
    var output = document.getElementById("output-path");
    if (output) output.disabled = running;
    ["chk-build-index", "chk-auto-open", "chk-preserve-structure"].forEach(function (id) {
        var node = document.getElementById(id);
        if (node) node.disabled = running;
    });
    updateInputSummary();      // keeps the clear button in step with the inputs
    renderConversionList();    // the remove buttons are recreated, so they read _conversionRunning
    applyThemeControlLock();     // the theme controls freeze with everything else
    applySettingsControlLock();  // and so does the settings page's management surface
}

// The dialog controls are disabled while one is open. This is a state lock, not
// only a visual cue: JavaScript is single threaded, so the click that opens a
// dialog disables the other controls before the next click can be dispatched,
// which is what stops two dialogs from ever overlapping.
function setDialogOpen(open) {
    _dialogOpen = open;
    ["btn-select-files", "btn-select-dir", "btn-select-output"].forEach(function (id) {
        var node = document.getElementById(id);
        if (node) node.disabled = open;
    });
}

// A TOC-independent helper: the GUI records the plan it confirmed, and the run
// uses that snapshot for every bridge call.
function resetLogAttention() {
    _logIssueCount = 0;
    _logIssueLevel = "";
    updateLogAttention();
}

function log(level, msg) {
    var area = document.getElementById("log-area");
    if (!area) return;
    var cls = level === "WARNING" ? "log-warn" : level === "ERROR" ? "log-err" : "log-info";
    var div = document.createElement("div");
    div.className = cls;
    div.textContent = msg;
    area.appendChild(div);
    while (LOG_CAPACITY < area.children.length) {
        area.removeChild(area.firstChild);
    }
    area.scrollTop = area.scrollHeight;
    if (level === "WARNING" || level === "ERROR") {
        _logIssueCount += 1;
        if (level === "ERROR" || !_logIssueLevel) {
            _logIssueLevel = level === "ERROR" ? "error" : "warning";
        }
        updateLogAttention();
    }
}
function appendLog(level, msg) { log(level, msg); }

// Workspace tabs
function setWorkspaceTab(name) {
    ["conversion", "preview", "log"].forEach(function(tabName) {
        document.getElementById("tab-" + tabName).classList.toggle("active", tabName === name);
        document.getElementById(tabName + "-page").classList.toggle("active", tabName === name);
    });
    var tabs = document.getElementById("workspace-tabs");
    tabs.setAttribute("data-active", name);
}
function showConversionTab() { setWorkspaceTab("conversion"); }
function showPreviewTab() { setWorkspaceTab("preview"); }
function showLogTab() { setWorkspaceTab("log"); }
