// Application state
var _lastOutputDir = "output";
var _lastOutputFile = "";
var _themeMode = "auto";
var _selectedTemplate = "modern";
var _templates = ["modern"];
var _inputSources = [];
var _conversionItems = [];
var _planWarnings = [];
var _planErrors = [];
var _planRevision = 0;
var _apiReady = false;
var _conversionRunning = false;
var _expandedItems = {};
var _logIssueCount = 0;
var _logIssueLevel = "";

function pathKey(value) {
    return String(value || "").replace(/\\/g, "/").toLowerCase();
}

function basename(value) {
    var parts = String(value || "").replace(/\\/g, "/").split("/");
    return parts[parts.length - 1] || value;
}

// Theme
function applyTheme(mode) {
    _themeMode = mode;
    var html = document.documentElement;
    html.removeAttribute("data-theme");
    if (mode === "light") {
        html.setAttribute("data-theme", "light");
    } else if (mode === "dark") {
        html.setAttribute("data-theme", "dark");
    }

    var btn = document.getElementById("themeToggleBtn");
    if (mode === "dark") {
        btn.textContent = "☼";
        btn.title = "浅色模式";
    } else {
        btn.textContent = "☾";
        btn.title = "深色模式";
    }
    try { localStorage.setItem("gui-theme", mode); } catch (e) {}
}

document.getElementById("themeToggleBtn").addEventListener("click", function() {
    applyTheme(_themeMode === "dark" ? "light" : "dark");
});

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
    tab.setAttribute("aria-label", hasIssues ? "日志，" + _logIssueCount + " 个问题" : "日志");
}

// The lock is state, not just disabled controls: dropping files or calling a
// mutator directly must not change the inputs of a run that is already in flight.
function setConversionRunning(running) {
    _conversionRunning = running;
    var runButton = document.querySelector(".btn-run");
    if (runButton) runButton.disabled = running;
    var templateButton = document.getElementById("template-select-btn");
    if (templateButton) templateButton.disabled = running;
    var output = document.getElementById("output-path");
    if (output) output.disabled = running;
    ["chk-build-index", "chk-auto-open", "chk-preserve-structure"].forEach(function (id) {
        var node = document.getElementById(id);
        if (node) node.disabled = running;
    });
    updateInputSummary();      // keeps the clear button in step with the inputs
    renderConversionList();    // the remove buttons are recreated, so they read _conversionRunning
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

function updateTemplatePreview(name) {
    var preview = document.getElementById("template-preview");
    if (!preview) return;

    var normalized = (name || "modern").toLowerCase();
    preview.classList.remove("preview-modern", "preview-office", "preview-vscode");
    if (normalized === "office") {
        preview.classList.add("preview-office");
    } else if (normalized === "vscode") {
        preview.classList.add("preview-vscode");
    } else {
        preview.classList.add("preview-modern");
    }
}

// Custom template select
function buildTemplateDropdown(items) {
    if (!Array.isArray(items) || items.length === 0) {
        items = ["modern"];
        log("WARNING", "模板列表为空，已回退为 modern");
    }
    _templates = items;
    if (_templates.indexOf(_selectedTemplate) === -1) _selectedTemplate = _templates[0];

    var dd = document.getElementById("template-select-dropdown");
    dd.innerHTML = "";
    _templates.forEach(function(templateName) {
        var item = document.createElement("div");
        item.className = "dropdown-item";
        item.classList.toggle("selected", templateName === _selectedTemplate);
        item.textContent = templateName;
        item.onclick = function(event) {
            event.stopPropagation();
            selectTemplate(templateName);
        };
        dd.appendChild(item);
    });
    document.getElementById("template-select-text").textContent = _selectedTemplate;
    updateTemplatePreview(_selectedTemplate);
}

function selectTemplate(name) {
    if (_conversionRunning) return;
    _selectedTemplate = name;
    document.getElementById("template-select-text").textContent = name;
    updateTemplatePreview(name);
    document.querySelectorAll("#template-select-dropdown .dropdown-item").forEach(function(item) {
        item.classList.toggle("selected", item.textContent === name);
    });
    closeTemplateDropdown();
    showPreviewTab();
}

function ensureDropdownPortal() {
    var dropdown = document.getElementById("template-select-dropdown");
    if (dropdown.parentElement !== document.body) document.body.appendChild(dropdown);
}

function positionTemplateDropdown() {
    var dropdown = document.getElementById("template-select-dropdown");
    var button = document.getElementById("template-select-btn");
    var rect = button.getBoundingClientRect();
    var gap = 4;
    var viewportPadding = 8;
    var maxHeight = 180;
    dropdown.style.left = rect.left + "px";
    dropdown.style.width = rect.width + "px";

    var spaceBelow = window.innerHeight - rect.bottom - viewportPadding;
    var spaceAbove = rect.top - viewportPadding;
    if (spaceBelow < 120 && spaceAbove > spaceBelow) {
        dropdown.style.maxHeight = Math.max(80, Math.min(maxHeight, spaceAbove - gap)) + "px";
        dropdown.style.top = "";
        dropdown.style.bottom = (window.innerHeight - rect.top + gap) + "px";
    } else {
        dropdown.style.maxHeight = Math.max(80, Math.min(maxHeight, spaceBelow - gap)) + "px";
        dropdown.style.bottom = "";
        dropdown.style.top = (rect.bottom + gap) + "px";
    }
}

function toggleTemplateDropdown() {
    var dropdown = document.getElementById("template-select-dropdown");
    var button = document.getElementById("template-select-btn");
    ensureDropdownPortal();
    if (dropdown.classList.contains("hidden")) {
        positionTemplateDropdown();
        dropdown.classList.remove("hidden");
        button.classList.add("open");
        setTimeout(function() {
            document.addEventListener("click", closeOnClickOutside);
            window.addEventListener("resize", positionTemplateDropdown);
            var leftColumn = document.querySelector(".left-column");
            if (leftColumn) leftColumn.addEventListener("scroll", closeTemplateDropdown);
        }, 50);
    } else {
        closeTemplateDropdown();
    }
}

function closeTemplateDropdown() {
    var dropdown = document.getElementById("template-select-dropdown");
    var button = document.getElementById("template-select-btn");
    if (dropdown) dropdown.classList.add("hidden");
    if (button) button.classList.remove("open");
    document.removeEventListener("click", closeOnClickOutside);
    window.removeEventListener("resize", positionTemplateDropdown);
    var leftColumn = document.querySelector(".left-column");
    if (leftColumn) leftColumn.removeEventListener("scroll", closeTemplateDropdown);
}

function closeOnClickOutside(event) {
    var wrap = document.getElementById("template-select-wrap");
    var dropdown = document.getElementById("template-select-dropdown");
    if (!wrap.contains(event.target) && !dropdown.contains(event.target)) closeTemplateDropdown();
}

// Input collection and preflight plan
function updateInputSummary() {
    var summary = document.getElementById("input-summary");
    var clearButton = document.getElementById("btn-clear-inputs");
    if (_inputSources.length === 0) {
        summary.textContent = "尚未选择文档";
        clearButton.disabled = true;
    } else {
        summary.textContent = "已添加 " + _inputSources.length + " 个输入来源";
        clearButton.disabled = false;
    }
}

async function addInputs(paths) {
    if (_conversionRunning) return;
    if (!Array.isArray(paths)) paths = [paths];
    var existing = {};
    _inputSources.forEach(function(path) { existing[pathKey(path)] = true; });
    paths.forEach(function(path) {
        var value = String(path || "").trim();
        var key = pathKey(value);
        if (value && !existing[key]) {
            _inputSources.push(value);
            existing[key] = true;
        }
    });
    updateInputSummary();
    await refreshConversionPlan(true);
}

async function removeInputSource(path) {
    if (_conversionRunning) return;
    var key = pathKey(path);
    _inputSources = _inputSources.filter(function(item) { return pathKey(item) !== key; });
    updateInputSummary();
    await refreshConversionPlan(true);
}

async function clearInputs() {
    if (_conversionRunning) return;
    // Invalidate every plan request already in flight BEFORE the state is reset, so
    // a response that arrives later cannot pass the revision guard and repopulate
    // the list we just emptied.
    ++_planRevision;
    _inputSources = [];
    _conversionItems = [];
    _planWarnings = [];
    _planErrors = [];
    _expandedItems = {};
    // The produced file belongs to the run we just reset; the output DIRECTORY is
    // deliberately kept, because clearing inputs does not invalidate a directory.
    _lastOutputFile = "";
    document.getElementById("btn-open-file").disabled = true;
    document.getElementById("statusBadge").textContent = "READY";
    document.getElementById("statusText").textContent = "就绪 - 选择 Markdown 文件开始转换";
    updateInputSummary();
    renderConversionList();
    showConversionTab();
}

async function selectFiles() {
    if (_conversionRunning) return;
    if (!_apiReady) return;
    var paths = await pywebview.api.select_input_files();
    if (paths && paths.length) await addInputs(paths);
}

async function selectDir() {
    if (_conversionRunning) return;
    if (!_apiReady) return;
    var path = await pywebview.api.select_input_directory();
    if (path) await addInputs([path]);
}

async function selectOutput() {
    if (_conversionRunning) return;
    if (!_apiReady) return;
    var path = await pywebview.api.select_output_directory();
    if (path) {
        document.getElementById("output-path").value = path;
        _lastOutputDir = path;
        await refreshConversionPlan(false);
    }
}

async function acceptDroppedInputs(paths) {
    if (_conversionRunning) return;
    setDropOverlay(false);
    if (paths && paths.length) {
        log("INFO", "已拖入 " + paths.length + " 个文件或目录来源。");
        await addInputs(paths);
    }
}

function setDropOverlay(active) {
    document.getElementById("drop-overlay").classList.toggle("hidden", !active);
}

document.addEventListener("dragleave", function(event) {
    if (!event.relatedTarget) setDropOverlay(false);
});

async function refreshConversionPlan(activateTab, snapshot) {
    var revision = ++_planRevision;
    if (_inputSources.length === 0) {
        _conversionItems = [];
        _planWarnings = [];
        _planErrors = [];
        renderConversionList();
        if (activateTab) showConversionTab();
        return null;
    }
    if (!_apiReady) return null;

    var source = snapshot || {};
    var output = source.output === undefined
        ? document.getElementById("output-path").value.trim() || "output"
        : source.output;
    var preserve = source.preserve_structure === undefined
        ? document.getElementById("chk-preserve-structure").checked
        : source.preserve_structure;
    var inputs = source.inputs === undefined ? _inputSources : source.inputs;
    var plan = await pywebview.api.prepare_conversion({
        inputs: inputs.slice(),
        output_dir: output,
        preserve_structure: preserve
    });
    if (revision !== _planRevision) return null;

    // The converter is the canonical authority for how an input is spelled: it
    // runs abspath plus normpath and reports the result in plan.inputs. Adopting it
    // here keeps identity comparisons consistent without teaching the GUI any
    // Windows path rules. Only interactive preflights adopt, and only after the
    // revision guard, so a stale response cannot rewrite the state.
    if (!snapshot && Array.isArray(plan.inputs)) {
        _inputSources = plan.inputs.slice();
        updateInputSummary();
    }

    _conversionItems = Array.isArray(plan.items) ? plan.items : [];
    _planWarnings = Array.isArray(plan.warnings) ? plan.warnings : [];
    _planErrors = Array.isArray(plan.errors) ? plan.errors : [];
    _lastOutputDir = plan.output_dir || output;
    renderConversionList();
    if (activateTab) showConversionTab();
    return plan;
}

function statusInfo(status) {
    var values = {
        pending: ["○", "待转换"],
        converting: ["●", "转换中"],
        success: ["✓", "完成"],
        warning: ["!", "警告"],
        error: ["×", "失败"],
        conflict: ["×", "冲突"],
        skipped: ["–", "未转换"]
    };
    return values[status] || values.pending;
}

function originLabel(origin) {
    return origin === "directory" ? "目录扫描" : origin === "dependency" ? "链接依赖" : "直接加入";
}

function appendDetailLine(container, label, value, className) {
    var line = document.createElement("div");
    line.className = "detail-line" + (className ? " " + className : "");
    var key = document.createElement("strong");
    key.textContent = label;
    var content = document.createElement("span");
    content.textContent = value || "—";
    content.title = value || "";
    line.appendChild(key);
    line.appendChild(content);
    container.appendChild(line);
}

function toggleConversionDetails(sourcePath) {
    var key = pathKey(sourcePath);
    _expandedItems[key] = !_expandedItems[key];
    renderConversionList();
}

function renderConversionList() {
    var list = document.getElementById("conversion-list");
    var empty = document.getElementById("conversion-empty");
    var filter = document.getElementById("conversion-filter").value.trim().toLowerCase();
    list.innerHTML = "";

    var visibleItems = _conversionItems.filter(function(item) {
        return !filter || String(item.relative_path || item.source_path).toLowerCase().indexOf(filter) >= 0;
    });
    visibleItems.forEach(function(item) {
        var itemKey = pathKey(item.source_path);
        var expanded = !!_expandedItems[itemKey];
        var row = document.createElement("div");
        row.className = "conversion-row status-" + (item.status || "pending");
        row.classList.toggle("is-expanded", expanded);
        row.setAttribute("role", "button");
        row.setAttribute("tabindex", "0");
        row.setAttribute("aria-expanded", String(expanded));
        row.title = expanded ? "点击收起详情" : "点击展开详情";
        row.onclick = function() { toggleConversionDetails(item.source_path); };
        row.onkeydown = function(event) {
            if (event.target !== row) return;
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                toggleConversionDetails(item.source_path);
            }
        };

        var status = document.createElement("span");
        status.className = "conversion-status";
        var info = statusInfo(item.status);
        status.textContent = info[0];
        status.title = info[1];

        var documentCell = document.createElement("span");
        documentCell.className = "conversion-document";
        var topLine = document.createElement("span");
        topLine.className = "document-topline";
        var title = document.createElement("strong");
        title.textContent = basename(item.source_path);
        var origin = document.createElement("span");
        origin.className = "origin-badge origin-" + (item.origin || "selected");
        origin.textContent = originLabel(item.origin);
        var expandHint = document.createElement("span");
        expandHint.className = "expand-hint";
        expandHint.textContent = expanded ? "收起" : "详情";
        topLine.appendChild(title);
        topLine.appendChild(origin);
        topLine.appendChild(expandHint);

        var meta = document.createElement("small");
        meta.className = "conversion-meta";
        var sourceRelative = item.relative_path || basename(item.source_path);
        var outputRelative = item.output_relative || basename(item.output_path);
        meta.textContent = sourceRelative + "  →  " + outputRelative;
        meta.title = sourceRelative + " → " + outputRelative;
        documentCell.appendChild(topLine);
        documentCell.appendChild(meta);
        if (item.warnings && item.warnings.length) {
            var warning = document.createElement("small");
            warning.className = "row-warning";
            warning.textContent = item.warnings.join("；");
            documentCell.appendChild(warning);
        }

        var action = document.createElement("button");
        action.className = "conversion-remove";
    action.disabled = _conversionRunning;
        action.textContent = "×";
        action.title = item.origin === "directory" ? "移除该目录来源" : "移除该文件";
        action.onclick = function(event) {
            event.stopPropagation();
            removeInputSource(item.input_path);
        };

        var details = document.createElement("div");
        details.className = "conversion-details";
        details.classList.toggle("hidden", !expanded);
        appendDetailLine(details, "源文件", item.source_path);
        appendDetailLine(details, "输出", item.output_path);
        appendDetailLine(details, "状态", info[1]);
        if (item.warnings && item.warnings.length) {
            appendDetailLine(details, "警告", item.warnings.join("；"), "detail-warning");
        }

        row.appendChild(status);
        row.appendChild(documentCell);
        row.appendChild(action);
        row.appendChild(details);
        list.appendChild(row);
    });

    empty.classList.toggle("hidden", _conversionItems.length !== 0);
    list.classList.toggle("hidden", _conversionItems.length === 0);

    var pending = _conversionItems.filter(function(item) {
        return item.status === "pending" || item.status === "converting";
    }).length;
    var warnings = _conversionItems.filter(function(item) { return item.status === "warning"; }).length;
    var errors = _conversionItems.filter(function(item) {
        return item.status === "error" || item.status === "conflict";
    }).length + _planErrors.length;
    document.getElementById("stat-total").textContent = _conversionItems.length;
    document.getElementById("stat-pending").textContent = pending;
    document.getElementById("stat-warning").textContent = warnings;
    document.getElementById("stat-error").textContent = errors;
    document.getElementById("conversion-tab-count").textContent = _conversionItems.length;

    var messages = document.getElementById("conversion-messages");
    messages.innerHTML = "";
    _planErrors.concat(_planWarnings).forEach(function(message, index) {
        var entry = document.createElement("div");
        entry.className = index < _planErrors.length ? "plan-error" : "plan-warning";
        entry.textContent = message;
        messages.appendChild(entry);
    });
}

function updateConversionStatus(sourcePath, status, warnings, outputPath) {
    var key = pathKey(sourcePath);
    _conversionItems.forEach(function(item) {
        if (pathKey(item.source_path) === key) {
            item.status = status;
            item.warnings = Array.isArray(warnings) ? warnings : [];
            if (outputPath) item.output_path = outputPath;
        }
    });
    renderConversionList();
}

// Conversion
async function runConvert() {
    if (!_apiReady) return;
    if (_inputSources.length === 0) {
        log("WARNING", "请选择或拖入 Markdown 文件或目录。");
        showConversionTab();
        return;
    }

    // Freeze the whole run at entry. The lock stops the GUI from drifting, and the
    // snapshot is what every bridge call of this run uses. The output directory is
    // taken from the UI and never from plan.output_dir, because the plan may
    // already hold the derived "<dir>-HTML" directory for a single-source run.
    setConversionRunning(true);
    var runInputs = _inputSources.slice();
    var runOutput = document.getElementById("output-path").value.trim() || "output";
    var runTemplate = getSelectedTemplate();
    var runBuildIndex = document.getElementById("chk-build-index").checked;
    var runAutoOpen = document.getElementById("chk-auto-open").checked;
    var runPreserveStructure = document.getElementById("chk-preserve-structure").checked;
    var snapshot = {
        inputs: runInputs,
        output: runOutput,
        preserve_structure: runPreserveStructure
    };

    try {
        resetLogAttention();
        var plan = await refreshConversionPlan(false, snapshot);
        if (!plan || _planErrors.length || _conversionItems.length === 0) {
            log("ERROR", _planErrors.join("；") || "转换清单为空。");
            showConversionTab();
            return;
        }

        await pywebview.api.set_configs({
            input: runInputs[0] || "",
            template: runTemplate,
            output: runOutput,
            build_index: runBuildIndex,
            auto_open: runAutoOpen,
            preserve_structure: runPreserveStructure
        });
        _lastOutputDir = runOutput;

        document.getElementById("statusBadge").textContent = "BUSY";
        document.getElementById("statusText").textContent = "正在转换 " + _conversionItems.length + " 个文档…";
        showConversionTab();

        var result;
        try {
            result = await pywebview.api.convert({
                inputs: runInputs.slice(),
                output_dir: runOutput,
                template: runTemplate,
                overwrite: true,
                build_index: runBuildIndex,
                auto_open: runAutoOpen,
                preserve_structure: runPreserveStructure
            });
        } catch (error) {
            result = {success: false, files: [], errors: [String(error)], documents: []};
        }

        (result.documents || []).forEach(function(documentResult) {
            updateConversionStatus(
                documentResult.source_path,
                documentResult.status || "success",
                documentResult.warnings || [],
                documentResult.output_path || documentResult.path || ""
            );
        });

        if (result.success) {
            document.getElementById("statusBadge").textContent = "DONE";
            document.getElementById("statusText").textContent = "转换完成 - " + result.files.length + " 个文件";
            log("INFO", "转换完成：共生成 " + result.files.length + " 个文件");
            log("INFO", "使用模板：" + runTemplate);
            _lastOutputDir = result.output_dir || runOutput;
            log("INFO", "输出目录：" + _lastOutputDir);
            if (result.files.length !== 0) {
                _lastOutputFile = result.entry_file || result.files[0];
                document.getElementById("btn-open-file").disabled = false;
                document.getElementById("btn-open-dir").disabled = false;
            }
        } else {
            _conversionItems.forEach(function(item) {
                // Only the backend may report a file failure. Anything the run
                // never reached is a terminal skipped state: calling it an error
                // would invent evidence, and leaving it pending would imply work
                // that is still coming. The run errors are not attached to these
                // items, because that would imply the files themselves failed.
                if (item.status === "pending" || item.status === "converting") {
                    item.status = "skipped";
                    item.warnings = [];
                }
            });
            renderConversionList();
            document.getElementById("statusBadge").textContent = "ERROR";
            document.getElementById("statusText").textContent = "转换出错";
        }

        (result.warnings || []).forEach(function(message) { log("WARNING", message); });
        (result.errors || []).forEach(function(message) { log("ERROR", message); });
        showConversionTab();
    } finally {
        // The single unlock point: preflight errors, a rejected set_configs, a
        // rejected convert and the happy path all leave the GUI unlocked.
        setConversionRunning(false);
    }
}

function getSelectedTemplate() { return _selectedTemplate; }

// Actions
async function openFile() {
    if (_lastOutputFile) await pywebview.api.open_file(_lastOutputFile);
}
async function openDir() {
    await pywebview.api.open_directory(_lastOutputDir);
}

// Initialization
function waitForApi(timeoutMs) {
    return new Promise(function(resolve, reject) {
        if (window.pywebview && pywebview.api) return resolve();
        var start = Date.now();
        var timer = setInterval(function() {
            if (window.pywebview && pywebview.api) {
                clearInterval(timer);
                resolve();
            } else if (Date.now() - start > timeoutMs) {
                clearInterval(timer);
                reject(new Error("pywebview API 未就绪，超时 " + timeoutMs + "ms"));
            }
        }, 50);
    });
}

async function init() {
    document.querySelectorAll(".accordion").forEach(function(details) {
        details.setAttribute("open", "");
    });
    try {
        var savedTheme = localStorage.getItem("gui-theme");
        if (savedTheme) applyTheme(savedTheme);
    } catch (e) {}

    buildTemplateDropdown(["modern"]);
    updateInputSummary();
    renderConversionList();
    showPreviewTab();
    log("INFO", "等待 pywebview API 就绪...");

    try {
        await waitForApi(5000);
        _apiReady = true;
        log("INFO", "pywebview API 已就绪，开始加载配置。");
    } catch (error) {
        log("ERROR", "pywebview API 超时: " + error.message);
        return;
    }

    try {
        var templates = await pywebview.api.get_templates();
        buildTemplateDropdown(templates);
        var config = await pywebview.api.get_config();
        config = config || {};
        selectTemplate(config.template || "modern");
        document.getElementById("output-path").value = config.output || "output";
        document.getElementById("chk-auto-open").checked = config.auto_open !== false;
        document.getElementById("chk-build-index").checked = config.build_index !== false;
        document.getElementById("chk-preserve-structure").checked = !!config.preserve_structure;
        _lastOutputDir = config.output || "output";
        showPreviewTab();
    } catch (error) {
        log("ERROR", "Init failed: " + error);
        buildTemplateDropdown(["modern"]);
    }
}

document.getElementById("output-path").addEventListener("change", function() {
    refreshConversionPlan(false);
});
document.getElementById("chk-preserve-structure").addEventListener("change", function() {
    refreshConversionPlan(true);
});

// Left-column scroll affordances
(function() {
    var column = document.querySelector(".left-column");
    var up = document.getElementById("scroll-arrow-up");
    var down = document.getElementById("scroll-arrow-down");
    if (!column || !up || !down) return;
    function updateArrows() {
        var atTop = column.scrollTop <= 0;
        var atBottom = column.scrollTop + column.clientHeight >= column.scrollHeight - 2;
        up.classList.toggle("hidden", atTop);
        down.classList.toggle("hidden", atBottom);
    }
    column.addEventListener("scroll", updateArrows);
    up.addEventListener("click", function() { column.scrollBy({top: -200, behavior: "smooth"}); });
    down.addEventListener("click", function() { column.scrollBy({top: 200, behavior: "smooth"}); });
    updateArrows();
    setTimeout(updateArrows, 250);
})();

init();
