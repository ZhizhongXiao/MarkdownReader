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
    if (_conversionRunning || _dialogOpen) return;
    if (!_apiReady) return;
    setDialogOpen(true);
    try {
        var paths = await pywebview.api.select_input_files();
        if (paths && paths.length) await addInputs(paths);
    } finally {
        setDialogOpen(false);
    }
}

async function selectDir() {
    if (_conversionRunning || _dialogOpen) return;
    if (!_apiReady) return;
    setDialogOpen(true);
    try {
        var path = await pywebview.api.select_input_directory();
        if (path) await addInputs([path]);
    } finally {
        setDialogOpen(false);
    }
}

async function selectOutput() {
    if (_conversionRunning || _dialogOpen) return;
    if (!_apiReady) return;
    setDialogOpen(true);
    try {
        var path = await pywebview.api.select_output_directory();
        if (path) {
            document.getElementById("output-path").value = path;
            _lastOutputDir = path;
            await refreshConversionPlan(false);
        }
    } finally {
        setDialogOpen(false);
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
    // The error stat counts documents. Plan messages are a different kind of
    // thing and already have their own place in the conversion tab, so adding
    // them here would make one number mean two units.
    var errors = _conversionItems.filter(function(item) {
        return item.status === "error" || item.status === "conflict";
    }).length;
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
