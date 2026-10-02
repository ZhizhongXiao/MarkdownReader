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

    renderPreviewNav();
    renderThemePreview();
    bindPreviewNav();
    updateInputSummary();
    renderConversionList();
    renderThemeSelection();
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
        // Phase 12 GUI closeout: no template list is asked for, and `config.template` is not read.
        // The page's theme surfaces are the preview stage and the carry selection; the theme a
        // document falls back to is the bridge's own bootstrap constant.
        var config = await pywebview.api.get_config();
        config = config || {};
        document.getElementById("output-path").value = config.output || "output";
        document.getElementById("chk-auto-open").checked = config.auto_open !== false;
        document.getElementById("chk-build-index").checked = config.build_index !== false;
        document.getElementById("chk-preserve-structure").checked = !!config.preserve_structure;
        _lastOutputDir = config.output || "output";
        var themeState = await pywebview.api.get_theme_state();
        applyThemeState(themeState);
        showPreviewTab();
    } catch (error) {
        log("ERROR", "Init failed: " + error);
        _previewTheme = BOOTSTRAP_THEME;
        renderThemePreview();
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
