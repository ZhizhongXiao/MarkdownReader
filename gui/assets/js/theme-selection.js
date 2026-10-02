// ── External theme selection (phase 9A) ────────────────────────────────────────
//
// Two concepts share one bridge call but stay separate here, because AGENTS section 17
// separates them: the template dropdown picks the document's default theme (builtin
// only), while this surface picks which installed user themes the next documents carry.
//
// The state has four row forms. `missing` and `invalid` come from the bridge fields, so a
// remembered id that cannot be used today is always shown as such and stays unselectable.
// `selected` and `available` describe the working selection itself, so a local change is
// visible before the bridge answers again. No form is ever derived from warning wording.
//
//   selected   selectable and in the working selection   checked, selectable
//   available  selectable but not in it                  unchecked, selectable
//   missing    in `missing`                              unchecked, not selectable
//   invalid    in `invalid` or `installed_invalid`        unchecked, not selectable

function themeRowState(id) {
    var state = _themeState || {};
    if ((state.missing || []).indexOf(id) !== -1) return "missing";
    if ((state.invalid || []).indexOf(id) !== -1) return "invalid";
    // Phase 9B2: an installed theme that fails the use-time gate is unusable whether or not the
    // configuration remembers it. Without this the page offered a broken installation as a usable
    // choice, and the failure only surfaced at the next conversion.
    if ((state.installed_invalid || []).indexOf(id) !== -1) return "invalid";
    return _themeSelection.indexOf(id) !== -1 ? "selected" : "available";
}

function themeStateLabel(state) {
    if (state === "selected") return "已选";
    if (state === "missing") return "未安装";
    if (state === "invalid") return "不可用";
    return "可添加";
}

// Remembered ids first, in their own order, then the installed ids nobody selected yet.
function themeRowOrder() {
    var state = _themeState || {};
    var rows = [];
    (_themeSelection || []).forEach(function (id) {
        if (rows.indexOf(id) === -1) rows.push(id);
    });
    (state.installed || []).forEach(function (id) {
        if (rows.indexOf(id) === -1) rows.push(id);
    });
    return rows;
}

function renderThemeSelection() {
    var list = document.getElementById("external-theme-list");
    if (!list) return;
    var empty = document.getElementById("external-theme-empty");
    var summary = document.getElementById("external-theme-summary");
    list.innerHTML = "";

    var rows = themeRowOrder();
    rows.forEach(function (id) {
        var rowState = themeRowState(id);
        var facts = previewFacts(id);
        var row = document.createElement("div");
        row.className = "theme-row";
        row.setAttribute("data-theme-id", id);
        row.setAttribute("data-theme-state", rowState);

        // One row, two independent controls (Phase 12 GUI closeout): the checkbox carries the
        // theme into the next document, and the row body shows it on the preview stage.
        var box = document.createElement("input");
        box.type = "checkbox";
        box.className = "theme-row-check";
        box.setAttribute("data-theme-id", id);
        box.checked = rowState === "selected";
        box.setAttribute("data-theme-state", rowState);
        box.addEventListener("change", function () { toggleExternalTheme(id); });
        row.appendChild(box);

        var name = document.createElement("span");
        name.className = "theme-row-name";
        name.textContent = (facts && facts.name) || id;
        row.appendChild(name);

        var desc = document.createElement("span");
        desc.className = "theme-row-desc";
        desc.textContent = (facts && facts.description) || "";
        row.appendChild(desc);

        row.addEventListener("click", function (event) {
            // A click on the checkbox is the carry control, never a row click: the two meanings
            // must not leak into each other.
            if (event.target && event.target.closest &&
                    event.target.closest("input.theme-row-check")) {
                return;
            }
            selectPreviewTheme(id);
        });

        var badge = document.createElement("span");
        badge.className = "theme-state theme-state-" + rowState;
        badge.textContent = themeStateLabel(rowState);
        row.appendChild(badge);

        // Only a remembered id can be forgotten, and only while it cannot be used: an installed
        // theme is carried by checking it, and an unusable installation nobody chose must not grow
        // a button that would have nothing to do (Phase 9B2).
        var remembered = _themeSelection.indexOf(id) !== -1;
        if (remembered && (rowState === "missing" || rowState === "invalid")) {
            var remove = document.createElement("button");
            remove.className = "theme-remove";
            remove.setAttribute("data-theme-action", "remove");
            remove.textContent = "移除";
            remove.title = "从本次选择中移除 " + id;
            remove.addEventListener("click", function () { removeConfiguredTheme(id); });
            row.appendChild(remove);
        }
        list.appendChild(row);
    });

    if (summary) {
        // Every count is taken from the rows on screen: the summary describes what the user can
        // see, and a remembered id that cannot be used today never counts. That is also why the
        // numbers no longer come from one backend sub-field -- `invalid` is configured-only since
        // Phase 9B2, so reading it here would have hidden an unusable installation.
        var counts = { selected: 0, missing: 0, invalid: 0 };
        rows.forEach(function (id) {
            var rowState = themeRowState(id);
            if (counts[rowState] !== undefined) counts[rowState] += 1;
        });
        summary.setAttribute("data-selected", String(counts.selected));
        summary.setAttribute("data-missing", String(counts.missing));
        summary.setAttribute("data-invalid", String(counts.invalid));
        summary.textContent = "已选 " + counts.selected + " · 缺失 " + counts.missing +
            " · 不可用 " + counts.invalid;
    }
    if (empty) empty.classList.toggle("hidden", rows.length !== 0);
    applyThemeControlLock();
}

// A missing or invalid theme is never selectable, and nothing on this surface may move
// while a run is in flight: the conversion already under way must not see the selection
// change beneath it.
function applyThemeControlLock() {
    var list = document.getElementById("external-theme-list");
    if (!list) return;
    for (var i = 0; i < list.children.length; i += 1) {
        var row = list.children[i];
        var rowState = row.getAttribute("data-theme-state");
        var unusable = rowState === "missing" || rowState === "invalid";
        var box = row.querySelector('input[type="checkbox"]');
        if (box) box.disabled = _conversionRunning || unusable;
        var remove = row.querySelector('[data-theme-action="remove"]');
        if (remove) remove.disabled = _conversionRunning;
    }
}

function toggleExternalTheme(id) {
    if (_conversionRunning) return;
    // A disabled checkbox is a hint, not a rule: a direct call must not select something that
    // cannot be used today (Phase 9B2), just like the settings actions against the terminal state.
    var rowState = themeRowState(id);
    if (rowState === "missing" || rowState === "invalid") return;
    var index = _themeSelection.indexOf(id);
    if (index === -1) {
        _themeSelection.push(id);          // a new choice goes to the end of the memory
    } else {
        _themeSelection.splice(index, 1);
    }
    renderThemeSelection();
    saveThemeSelection();
}

// Only an explicit removal may drop a remembered id that cannot be used today -- the same
// surfaces must not shrink the memory as a side effect of anything else (AGENTS section 17).
function removeConfiguredTheme(id) {
    if (_conversionRunning) return;
    var index = _themeSelection.indexOf(id);
    if (index === -1) return;
    _themeSelection.splice(index, 1);
    renderThemeSelection();
    saveThemeSelection();
}

// One write at a time. The newest selection wins and is committed once the write in
// flight settled, so the file can never end up holding a state older than the surface.
// The drain reports whether the selection is now confirmed in the file, and a failure
// discards every assumption rather than replaying it.
function saveThemeSelection() {
    _themeSavePending = _themeSelection.slice();
    if (!_themeSaveInFlight) _themeSaveDrain = drainThemeSaves();
    return _themeSaveDrain;
}

async function drainThemeSaves() {
    _themeSaveInFlight = true;
    try {
        while (_themeSavePending !== null) {
            var payload = _themeSavePending;
            _themeSavePending = null;
            try {
                await pywebview.api.set_configs({ external_themes: payload });
                _themeConfirmed = payload.slice();
            } catch (error) {
                // The surface may have assumed several changes by then, so it must not try
                // to undo them one by one: ask the bridge what is true and rebuild from it.
                _themeSavePending = null;
                log("ERROR", "保存外置主题选择失败：" + error);
                try {
                    await reloadThemeState();
                } catch (reloadError) {
                    // The bridge cannot say what is true either, so fall back to the last
                    // selection that was actually persisted -- never to the startup
                    // snapshot, which may predate a save that already succeeded.
                    log("ERROR", "读取外置主题状态失败：" + reloadError);
                    _themeSelection = _themeConfirmed.slice();
                    renderThemeSelection();
                }
                return false;
            }
        }
        return true;
    } finally {
        _themeSaveInFlight = false;
    }
}

// The run's gate. A run reads the selection back from config.json, so it must not start
// while a theme write is on its way -- and it must not start at all when that write
// failed, because then the choice the user just made is not in effect.
async function waitForThemeSaves() {
    while (_themeSaveInFlight || _themeSavePending !== null) {
        if (!_themeSaveDrain) _themeSaveDrain = drainThemeSaves();
        if ((await _themeSaveDrain) === false) return false;
    }
    return true;
}

// `configured` is the memory, so the working selection starts as a copy of it and the
// bridge's warnings are reported as warnings: a theme that is gone or broken must not
// turn into a failed run (AGENTS section 17).
function applyThemeState(state) {
    _themeState = state || {};
    _themeSelection = (_themeState.configured || []).slice();
    _themeConfirmed = _themeSelection.slice();
    _themePreviews = (_themeState.previews && typeof _themeState.previews === "object")
        ? _themeState.previews
        : {};
    // Phase 12 GUI closeout: the preview facts travel with the state, and the preview stage keeps
    // the theme the user is looking at while it is still available. A fresh session starts at the
    // bootstrap theme because that is where `_previewTheme` begins -- and it never reads the
    // payload's own default, which is not a GUI state any more.
    if (!previewTargetAvailable(_previewTheme)) _previewTheme = BOOTSTRAP_THEME;
    renderPreviewNav();
    renderThemeSelection();
    renderThemePreview();
    (_themeState.warnings || []).forEach(function (message) { log("WARNING", message); });
}

async function reloadThemeState() {
    var state = await pywebview.api.get_theme_state();
    applyThemeState(state);
}
