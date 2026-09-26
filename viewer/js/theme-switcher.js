    // ═══════════════════════════════════════════════════════════════
    // Module 14: Theme switch — the visual theme, not light/dark
    // ═══════════════════════════════════════════════════════════════
    // Every builtin theme ships in the document (Phase 6C), so switching is a CSS
    // state change and never a re-render: html[data-theme-id] selects the theme's
    // tokens, body.theme-<id> selects its component rules. Light/dark is the other
    // axis (html[data-theme], owned by Module 10) and the two never touch each other.
    //
    // The menu markup and the document's default theme come from the assembler, so
    // the page is already correct before this script runs; the module wires behaviour.
    var THEME_ID_ATTRIBUTE = "data-theme-id";
    var THEME_STORAGE_KEY = "markdownreader-theme-id";
    var THEME_CLASS_PREFIX = "theme-";

    function themeOptions() {
        var menu = document.getElementById("theme-menu");
        if (!menu) return [];
        return Array.prototype.slice.call(menu.querySelectorAll("[data-theme-id]"));
    }

    function knownThemeIds() {
        return themeOptions().map(function (option) {
            return option.getAttribute("data-theme-id");
        });
    }

    function documentThemeId() {
        return document.documentElement.getAttribute(THEME_ID_ATTRIBUTE) || "";
    }

    function applyThemeId(themeId) {
        document.documentElement.setAttribute(THEME_ID_ATTRIBUTE, themeId);
        // Only our own classes are removed: any other product class on <body> has to
        // survive a theme switch, which is why className is never reassigned.
        var body = document.body;
        Array.prototype.slice.call(body.classList).forEach(function (name) {
            if (name.indexOf(THEME_CLASS_PREFIX) === 0) body.classList.remove(name);
        });
        body.classList.add(THEME_CLASS_PREFIX + themeId);
    }

    function saveThemeId(themeId) {
        try { localStorage.setItem(THEME_STORAGE_KEY, themeId); } catch (e) {}
    }

    function restoredThemeId() {
        var saved = null;
        try { saved = localStorage.getItem(THEME_STORAGE_KEY); } catch (e) {}
        // A stored id is honoured only when this document actually carries that
        // theme; anything stale falls back to the document's own default (the theme
        // its author converted with) rather than to a hardcoded one.
        if (saved && knownThemeIds().indexOf(saved) !== -1) return saved;
        return documentThemeId();
    }

    function setThemeMenuOpen(open) {
        var menu = document.getElementById("theme-menu");
        var button = document.getElementById("btn-theme");
        if (!menu || !button) return;
        if (open) menu.removeAttribute("hidden");
        else menu.setAttribute("hidden", "");
        button.setAttribute("aria-expanded", open ? "true" : "false");
    }

    function isThemeMenuOpen() {
        var menu = document.getElementById("theme-menu");
        return !!menu && !menu.hasAttribute("hidden");
    }

    function syncThemeMenu() {
        var active = documentThemeId();
        themeOptions().forEach(function (option) {
            option.classList.toggle("active", option.getAttribute("data-theme-id") === active);
        });
    }

    function initThemeSwitcher() {
        var button = document.getElementById("btn-theme");
        var menu = document.getElementById("theme-menu");
        if (!button || !menu) return;

        var restored = restoredThemeId();
        if (restored) applyThemeId(restored);
        setThemeMenuOpen(false);
        syncThemeMenu();

        button.addEventListener("click", function (event) {
            event.stopPropagation();
            setThemeMenuOpen(!isThemeMenuOpen());
        });

        menu.addEventListener("click", function (event) {
            var option = event.target.closest("[data-theme-id]");
            if (!option) return;
            var themeId = option.getAttribute("data-theme-id");
            applyThemeId(themeId);
            saveThemeId(themeId);
            syncThemeMenu();
            setThemeMenuOpen(false);
        });

        document.addEventListener("click", function (event) {
            if (!isThemeMenuOpen()) return;
            if (menu.contains(event.target) || button.contains(event.target)) return;
            setThemeMenuOpen(false);
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") setThemeMenuOpen(false);
        });
    }

