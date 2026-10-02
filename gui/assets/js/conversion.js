// Conversion
async function runConvert() {
    if (!_apiReady || _removalTerminal) return;
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
    var runBuildIndex = document.getElementById("chk-build-index").checked;
    var runAutoOpen = document.getElementById("chk-auto-open").checked;
    var runPreserveStructure = document.getElementById("chk-preserve-structure").checked;
    var snapshot = {
        inputs: runInputs,
        output: runOutput,
        preserve_structure: runPreserveStructure
    };

    try {
        // The selection has to be persisted before the run reads it back, and a selection
        // that could not be persisted cancels the run: converting would silently use the
        // configuration the user just replaced.
        if (!(await waitForThemeSaves())) {
            log("ERROR", "外置主题选择未能保存，本次转换已取消。");
            return;
        }
        resetLogAttention();
        var plan = await refreshConversionPlan(false, snapshot);
        if (!plan || _planErrors.length || _conversionItems.length === 0) {
            log("ERROR", _planErrors.join("；") || "转换清单为空。");
            showConversionTab();
            return;
        }

        await pywebview.api.set_configs({
            input: runInputs[0] || "",
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
