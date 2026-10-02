// ── Settings surface (phase 9B1) ──────────────────────────────────────────────
//
// The settings page owns a different fact than the main page (AGENTS section 17). The main
// page answers "which themes does this document carry"; this page answers "what is
// installed here, and does it still work" through get_theme_inventory(). Neither surface
// writes the other's fact: nothing here calls set_configs, and the main page never installs
// or removes a theme.
//
// The page loads lazily -- opening it is what asks the bridge -- so it costs nothing at
// startup and cannot change what the main page does while it stays closed.

var _themeInventory = null;
// Closing is a two-step act -- re-read the main page, then reveal it -- so it needs a state
// of its own: a second Back press must not start a second read, and the main page must not
// appear while the rows it would show are known to be stale.
var _settingsClosing = false;
// Phase 11: the removal is terminal, so the page keeps two mirrors of the backend state -- one
// management action in flight, and the terminal flag the confirmation sets. The backend stays
// the authority; these only decide what the page keeps clickable.
var _settingsActionInFlight = 0;
var _removalAvailable = false;
var _removalItems = [];
var _removalTerminal = false;
var _removalConfirmed = false;
var _removalTimer = null;
var _removalDeadline = 0;
var REMOVAL_SECONDS = 5;

var STORAGE_FACT_LABELS = [
    ["mode", "运行模式"],
    ["user_data_root", "用户数据目录"],
    ["config_path", "配置文件"],
    ["external_themes_root", "外置主题目录"],
    ["runtime_root", "runtime 目录"],
    ["runtime_note", "说明"]
];

var ABOUT_FACT_LABELS = [
    ["name", "应用"],
    ["version", "版本"],
    ["renderer_version", "渲染器"],
    ["python", "Python"],
    ["mode", "运行模式"]
];

function setSettingsView(isOpen) {
    var app = document.querySelector(".app");
    var button = document.getElementById("btn-settings");
    if (app) app.classList.toggle("settings-open", isOpen);
    if (button) {
        button.title = isOpen ? "返回主页面" : "设置";
        button.setAttribute("aria-label", isOpen ? "返回主页面" : "打开设置");
    }
}

function toggleSettings() {
    var app = document.querySelector(".app");
    if (app && app.classList.contains("settings-open")) {
        closeSettings();
        return;
    }
    openSettings();
}

function openSettings() {
    var page = document.getElementById("settings-page");
    if (!page || _settingsClosing) return;
    page.classList.remove("hidden");
    setSettingsView(true);
    applySettingsControlLock();
    loadSettingsFacts();
}

// The main page is revealed only after its own state has been re-read: `closeSettings()` is
// the one place that knows a visit may have changed what is installed, so it is also the one
// place that must not hand the user a main page it knows to be stale. A failed re-read keeps
// the settings page in front -- and Back stays pressable, so that state is a retry rather
// than a dead end.
async function closeSettings() {
    if (_settingsClosing) return;
    _settingsClosing = true;
    applySettingsControlLock();
    try {
        await reloadThemeState();
        var page = document.getElementById("settings-page");
        if (page) page.classList.add("hidden");
        setSettingsView(false);
    } catch (error) {
        log("ERROR", "读取外置主题状态失败：" + error);
    } finally {
        _settingsClosing = false;
        applySettingsControlLock();
    }
}

async function loadSettingsFacts() {
    await refreshInventory();
    // The storage reply is read once and used twice: the fact rows are rendered from it, and
    // the removal surface takes its capability and its promises from the same reply.
    try {
        var storage = await pywebview.api.get_storage_info();
        renderFacts("settings-storage", storage, STORAGE_FACT_LABELS);
        applyStorageFacts(storage);
    } catch (error) {
        log("ERROR", "读取存储信息失败：" + error);
    }
    await loadFacts("settings-about", function () { return pywebview.api.get_about_info(); },
        ABOUT_FACT_LABELS, "读取版本信息失败：");
}

async function loadFacts(rootId, request, labels, failure) {
    try {
        renderFacts(rootId, await request(), labels);
    } catch (error) {
        log("ERROR", failure + error);
    }
}

// Every fact is rendered from the reply, never from a constant: the page must not be able
// to show a path this build does not actually use.
function renderFacts(rootId, facts, labels) {
    var root = document.getElementById(rootId);
    if (!root) return;
    root.innerHTML = "";
    labels.forEach(function (entry) {
        var key = entry[0];
        var row = document.createElement("div");
        row.className = "fact-row";
        row.setAttribute("data-fact", key);

        var label = document.createElement("span");
        label.className = "fact-label";
        label.textContent = entry[1];

        var value = document.createElement("span");
        value.className = "fact-value";
        value.setAttribute("data-fact-value", "");
        var raw = facts ? facts[key] : null;
        value.textContent = raw === null || raw === undefined || raw === "" ? "—" : String(raw);

        row.appendChild(label);
        row.appendChild(value);
        root.appendChild(row);
    });
}

// Phase 11: the removal surface. The page only presents and asks -- it never deletes, and it
// does not decide whether this build may remove anything: `removal_available` and
// `removal_items` are bridge facts, and the confirmation sends exactly one request.
function applyStorageFacts(storage) {
    _removalAvailable = !!(storage && storage.removal_available);
    _removalItems = storage && Array.isArray(storage.removal_items)
        ? storage.removal_items.slice() : [];
    var entry = document.getElementById("btn-remove-user-data");
    if (entry) entry.classList.toggle("hidden", !_removalAvailable);
    renderRemovalItems();
    applySettingsControlLock();
}

function renderRemovalItems() {
    var root = document.getElementById("user-data-items");
    if (!root) return;
    root.innerHTML = "";
    _removalItems.forEach(function (item) {
        var row = document.createElement("div");
        row.className = "fact-row";
        row.setAttribute("data-removal-item", String(item.key || ""));

        var label = document.createElement("span");
        label.className = "fact-label";
        label.textContent = String(item.label || item.key || "");

        var value = document.createElement("span");
        value.className = "fact-value";
        value.textContent = String(item.path || "");

        row.appendChild(label);
        row.appendChild(value);
        root.appendChild(row);
    });
}

function openUserDataConfirmation() {
    if (!_removalAvailable || _removalTerminal) return;
    renderRemovalItems();
    var modal = document.getElementById("user-data-confirm");
    if (modal) modal.classList.remove("hidden");
    startRemovalCountdown();
}

// Five seconds, always from scratch: the confirmation is a gate rather than a decoration, so
// closing and reopening it must not carry a finished countdown over.
function startRemovalCountdown() {
    var confirm = document.getElementById("btn-user-data-confirm");
    var label = document.getElementById("user-data-countdown");
    if (_removalTimer !== null) clearInterval(_removalTimer);
    _removalDeadline = Date.now() + REMOVAL_SECONDS * 1000;
    if (confirm) confirm.disabled = true;
    if (label) label.textContent = String(REMOVAL_SECONDS);
    _removalTimer = setInterval(function () {
        var left = Math.ceil((_removalDeadline - Date.now()) / 1000);
        if (left <= 0) {
            clearInterval(_removalTimer);
            _removalTimer = null;
            if (label) label.textContent = "0";
            if (confirm) confirm.disabled = false;
            return;
        }
        if (label) label.textContent = String(left);
    }, 250);
}

function cancelUserDataRemoval() {
    if (_removalTimer !== null) {
        clearInterval(_removalTimer);
        _removalTimer = null;
    }
    var modal = document.getElementById("user-data-confirm");
    if (modal) modal.classList.add("hidden");
    var confirm = document.getElementById("btn-user-data-confirm");
    if (confirm) confirm.disabled = true;
    var label = document.getElementById("user-data-countdown");
    if (label) label.textContent = String(REMOVAL_SECONDS);
}

async function confirmUserDataRemoval() {
    var confirm = document.getElementById("btn-user-data-confirm");
    if (_removalConfirmed || !_removalAvailable || (confirm && confirm.disabled)) return;
    // The lock is provisional: it keeps the page from starting new work while the backend decides,
    // and an explicit refusal hands the session straight back.
    _removalConfirmed = true;
    _removalTerminal = true;
    applySettingsControlLock();
    try {
        var reply = await pywebview.api.request_user_data_removal();
        if (reply && reply.ok === false) {
            // The backend is the authority and it said no -- something was still in flight. Only a
            // structured refusal reopens the page: a rejected promise usually means the accepted
            // request already destroyed the window, and reopening write access after that would
            // misread a torn-down session as a refusal.
            log("ERROR", "移除用户数据被拒绝：" + (reply.error || "未知原因"));
            _removalConfirmed = false;
            _removalTerminal = false;
            applySettingsControlLock();
        }
    } catch (error) {
        log("ERROR", "移除用户数据请求失败：" + error);
    }
}

// The installed list answers "what is here", while the main page answers "what does the
// document carry": the settings page renders without consulting the carry set, and shows
// the bridge's own verdict per row instead of guessing it from a selection state.
async function refreshInventory() {
    try {
        applyThemeInventory(await pywebview.api.get_theme_inventory());
    } catch (error) {
        log("ERROR", "读取已安装主题失败：" + error);
    }
}

function applyThemeInventory(inventory) {
    _themeInventory = inventory || {};
    var root = document.getElementById("settings-theme-root");
    if (root) root.textContent = _themeInventory.root || "—";
    renderThemeInventory();
}

function renderThemeInventory() {
    var list = document.getElementById("settings-theme-list");
    if (!list) return;
    var rows = (_themeInventory && _themeInventory.installed) || [];
    list.innerHTML = "";
    rows.forEach(function (entry) {
        var row = document.createElement("div");
        row.className = "settings-theme-row";
        row.setAttribute("data-theme-id", entry.id);
        row.setAttribute("data-theme-valid", entry.valid ? "true" : "false");

        var name = document.createElement("span");
        name.className = "settings-theme-name";
        name.textContent = entry.id;
        row.appendChild(name);

        var badge = document.createElement("span");
        badge.className = "theme-state theme-state-" + (entry.valid ? "selected" : "invalid");
        badge.textContent = entry.valid ? "可用" : "不可用";
        row.appendChild(badge);

        if (!entry.valid && entry.reason) {
            var reason = document.createElement("span");
            reason.className = "settings-theme-reason";
            reason.setAttribute("data-theme-reason", "");
            reason.textContent = entry.reason;
            row.appendChild(reason);
        }

        var remove = document.createElement("button");
        remove.className = "theme-remove";
        remove.setAttribute("data-theme-action", "remove");
        remove.textContent = "移除";
        remove.title = "卸载 " + entry.id;
        remove.addEventListener("click", function () { removeInstalledTheme(entry.id); });
        row.appendChild(remove);
        list.appendChild(row);
    });

    var empty = document.getElementById("settings-theme-empty");
    if (empty) empty.classList.toggle("hidden", rows.length !== 0);
    applySettingsControlLock();
}

// The management surface freezes while a run is in flight (the run resolves themes when it
// starts, so a theme that vanishes underneath it would turn a healthy conversion into a
// failure) and while the page is closing (the facts on screen are about to be replaced).
// The closing state also gates the actions themselves, because a disabled button is a hint,
// not a rule: a direct call must not slip past it either.
function applySettingsControlLock() {
    var locked = _conversionRunning || _settingsClosing || _removalTerminal;
    ["btn-import-theme", "btn-export-theme-template", "btn-open-theme-location"]
        .forEach(function (id) {
            var button = document.getElementById(id);
            if (button) button.disabled = locked;
        });
    var back = document.getElementById("btn-settings");
    if (back) back.disabled = _settingsClosing || _removalTerminal;
    // The removal entry waits for a quieter moment than the rest: an action that is still
    // writing has to finish before the confirmation may even be opened.
    var entry = document.getElementById("btn-remove-user-data");
    if (entry) entry.disabled = locked || _settingsActionInFlight !== 0;
    var list = document.getElementById("settings-theme-list");
    if (!list) return;
    for (var i = 0; i < list.children.length; i += 1) {
        var remove = list.children[i].querySelector('[data-theme-action="remove"]');
        if (remove) remove.disabled = locked;
    }
}

// A refusal is a normal outcome, not an exception: every management call answers with
// {ok, error}, and a rejected promise is reported through the same path, so no failure can
// leave the page waiting for an answer that will never arrive.
async function runSettingsAction(request, describe) {
    _settingsActionInFlight += 1;
    applySettingsControlLock();
    try {
        var result = await request();
        if (result && result.ok === false) {
            log("ERROR", describe + "失败：" + (result.error || "未知原因"));
            return null;
        }
        return result || {};
    } catch (error) {
        log("ERROR", describe + "失败：" + error);
        return null;
    } finally {
        // The removal entry stays disabled while an action is writing: "nothing is in flight"
        // is what the backend checks too, and this is its UI mirror.
        _settingsActionInFlight -= 1;
        applySettingsControlLock();
    }
}

async function importTheme() {
    if (_conversionRunning || _settingsClosing || _removalTerminal) return;
    var result = await runSettingsAction(
        function () { return pywebview.api.import_theme({}); }, "导入外置主题");
    if (!result) return;
    log("INFO", "已安装外置主题：" + (result.id || ""));
    await refreshInventory();
}

async function removeInstalledTheme(id) {
    if (_conversionRunning || _settingsClosing || _removalTerminal) return;
    var result = await runSettingsAction(
        function () { return pywebview.api.remove_theme(id); }, "卸载外置主题");
    if (!result) return;
    log("INFO", "已卸载外置主题：" + id);
    await refreshInventory();
}

async function exportThemeTemplate() {
    if (_conversionRunning || _settingsClosing || _removalTerminal) return;
    var result = await runSettingsAction(
        function () { return pywebview.api.export_theme_template({}); }, "导出主题模板");
    if (!result) return;
    log("INFO", "主题模板已导出：" + (result.path || ""));
}

async function openThemeLocation() {
    if (_conversionRunning || _settingsClosing || _removalTerminal) return;
    var result = await runSettingsAction(
        function () { return pywebview.api.open_theme_location(); }, "打开主题目录");
    if (!result) return;
    log("INFO", "主题目录：" + (result.path || ""));
}
