    // ═══════════════════════════════════════════════════════════════
    // Module 10: Dark Mode
    // ═══════════════════════════════════════════════════════════════
    var themeStorageKey = "markdownreader-theme";
    function applyTheme(mode) {
        if (mode === "dark") document.documentElement.setAttribute("data-theme", "dark");
        else document.documentElement.removeAttribute("data-theme");
        var btn = document.getElementById("btn-dark-mode");
        if (btn) { btn.textContent = mode === "dark" ? "☀️" : "🌙"; btn.title = mode === "dark" ? "浅色模式" : "暗色模式"; }
    }
    function detectSystemTheme() { return (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light"; }
    function initDarkMode() {
        var btn = document.getElementById("btn-dark-mode"); if (!btn) return;
        var saved = null; try { saved = localStorage.getItem(themeStorageKey); } catch (e) {}
        applyTheme(saved || detectSystemTheme());
        btn.addEventListener("click", function () { var m = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"; applyTheme(m); try { localStorage.setItem(themeStorageKey, m); } catch (e) {} });
    }

