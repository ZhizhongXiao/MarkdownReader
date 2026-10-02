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
    if (btn) {
        btn.title = mode === "dark" ? "浅色模式" : "深色模式";
        btn.setAttribute("aria-label", btn.title);
    }
    try { localStorage.setItem("gui-theme", mode); } catch (e) {}
}

var themeToggleButton = document.getElementById("themeToggleBtn");
if (themeToggleButton) themeToggleButton.addEventListener("click", function () {
    applyTheme(_themeMode === "dark" ? "light" : "dark");
});
