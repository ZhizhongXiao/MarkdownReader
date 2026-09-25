    // ═══════════════════════════════════════════════════════════════
    // TOC panel toggle (sidebar collapse to narrow strip)
    // ═══════════════════════════════════════════════════════════════
    var TOC_PANEL_STORAGE = "markdownreader-toc-panel-collapsed";
    function syncTocPanelButton() {
        var sidebar = document.getElementById("toc-sidebar");
        var btn = document.getElementById("btn-toggle-toc-panel");
        if (!btn) return;
        var isCollapsed = !!(sidebar && sidebar.classList.contains("collapsed"));
        var label = isCollapsed ? "展开侧边栏" : "折叠侧边栏";
        btn.title = label;
        btn.setAttribute("aria-label", label);
        btn.setAttribute("aria-expanded", String(!isCollapsed));
    }
    function toggleTocPanel() {
        var sidebar = document.getElementById("toc-sidebar");
        var container = document.querySelector(".viewer-container");
        if (!sidebar || !container) return;
        sidebar.classList.toggle("collapsed");
        container.classList.toggle("toc-collapsed");
        var isCollapsed = sidebar.classList.contains("collapsed");
        syncTocPanelButton();
        try { localStorage.setItem(TOC_PANEL_STORAGE, String(isCollapsed)); } catch (e) {}
    }
    function restoreTocPanel() {
        try {
            if (localStorage.getItem(TOC_PANEL_STORAGE) === "true") {
                var sidebar = document.getElementById("toc-sidebar");
                var container = document.querySelector(".viewer-container");
                if (sidebar) sidebar.classList.add("collapsed");
                if (container) container.classList.add("toc-collapsed");
            }
        } catch (e) {}
        syncTocPanelButton();
    }

    function initToolbar() {
        var btn;
        (btn = document.getElementById("btn-toggle-toc-panel")) && btn.addEventListener("click", toggleTocPanel);
        (btn = document.getElementById("btn-expand-all-content")) && btn.addEventListener("click", expandOneLevel);
        (btn = document.getElementById("btn-collapse-all-content")) && btn.addEventListener("click", collapseOneLevel);
        (btn = document.getElementById("btn-print")) && btn.addEventListener("click", function () { window.print(); });
    }

