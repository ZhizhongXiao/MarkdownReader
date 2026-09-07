/* ================================================================
   MDViewer — Viewer JavaScript (shared across all templates)
   v4.0 — TOC panel toggle, fixed step-wise fold, auto-numbering fix
   ================================================================ */

(function () {
    "use strict";

    // Deferred DOM references — populated by cacheDom() inside init()
    var tocBody = null;
    var contentArea = null;
    var markdownBody = null;

    // Step-wise content fold state
    var currentExpandedLevel = 6;   // 0=nothing visible, ..., 6=all visible
    var FOLD_STORAGE = "mdviewer-expandlevel";

    function getHeadingLevel(el) {
        var tag = el.tagName.toUpperCase();
        if (tag.length === 2 && tag[0] === "H") return parseInt(tag[1], 10);
        return 0;
    }

    function getContentHeadings() {
        return markdownBody.querySelectorAll("h1[id], h2[id], h3[id], h4[id], h5[id], h6[id]");
    }

    // ═══════════════════════════════════════════════════════════════
    // cacheDom — must be called AFTER DOMContentLoaded
    // ═══════════════════════════════════════════════════════════════
    function cacheDom() {
        tocBody = document.getElementById("toc-body");
        contentArea = document.getElementById("content-area");
        markdownBody = document.getElementById("markdown-body");
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 1: TOC click jump (Flat TOC)
    // ═══════════════════════════════════════════════════════════════
    function initTocClickJump() {
        tocBody.addEventListener("click", function (event) {
            if (event.target.closest(".toc-toggle")) return;
            var row = event.target.closest(".toc-row");
            if (!row) return;
            var link = row.querySelector(".toc-link");
            if (!link) return;
            var href = link.getAttribute("href");
            if (!href || !href.startsWith("#")) return;
            var targetId = href.substring(1);
            var targetElement = document.getElementById(targetId);
            if (targetElement) {
                event.preventDefault();
                targetElement.scrollIntoView({ behavior: "smooth" });
            }
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 2: Scroll Spy — Flat TOC
    // ═══════════════════════════════════════════════════════════════
    function autoExpandParents(row) {
        // Walk backwards to find parent-level rows and ensure they are expanded
        var currentLevel = parseInt(row.getAttribute("data-level"), 10);
        var prev = row.previousElementSibling;
        while (prev) {
            var plevel = parseInt(prev.getAttribute("data-level"), 10);
            if (plevel < currentLevel) {
                // This is a parent — ensure expanded and not hiding children
                prev.classList.add("is-expanded");
                prev.classList.remove("is-collapsed");
                // Show its immediate children
                unfoldImmediateChildren(prev);
                currentLevel = plevel;
            }
            prev = prev.previousElementSibling;
        }
    }

    function unfoldImmediateChildren(parentRow) {
        var parentLevel = parseInt(parentRow.getAttribute("data-level"), 10);
        var sibling = parentRow.nextElementSibling;
        while (sibling) {
            var sLevel = parseInt(sibling.getAttribute("data-level"), 10);
            if (sLevel <= parentLevel) break;
            if (sLevel === parentLevel + 1) {
                sibling.classList.remove("is-hidden-by-collapse");
            }
            sibling = sibling.nextElementSibling;
        }
    }

    function initScrollSpy() {
        var allRows = tocBody.querySelectorAll(".toc-row");
        function activateTocRow(id) {
            allRows.forEach(function (row) { row.classList.remove("active"); });
            var target = tocBody.querySelector('.toc-row[data-id="' + id + '"]');
            if (target) {
                target.classList.add("active");
                autoExpandParents(target);
                target.scrollIntoView({ block: "nearest", behavior: "smooth" });
            }
        }
        var headingElements = getContentHeadings();
        if (headingElements.length > 0 && "IntersectionObserver" in window) {
            var observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) activateTocRow(entry.target.id);
                });
            }, { root: contentArea, rootMargin: "-5% 0px -85% 0px", threshold: 0 });
            headingElements.forEach(function (h) { observer.observe(h); });
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 3: Flat TOC folding
    // ═══════════════════════════════════════════════════════════════
    var TOC_FOLD_STORAGE = "mdviewer-toc-collapsed-v2";
    function initTocFold() {
        var saved = null;
        try { saved = JSON.parse(localStorage.getItem(TOC_FOLD_STORAGE) || "[]"); } catch (e) { saved = []; }

        tocBody.querySelectorAll(".toc-toggle").forEach(function (btn) {
            var row = btn.closest(".toc-row");
            var id = row.getAttribute("data-id");
            if (saved.indexOf(id) !== -1) {
                row.classList.add("is-collapsed");
                row.classList.remove("is-expanded");
                applyChildrenVisibility(row, true);
            } else {
                row.classList.add("is-expanded");
            }

            btn.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                var r = this.closest(".toc-row");
                var isCollapsing = !r.classList.contains("is-collapsed");
                if (isCollapsing) {
                    r.classList.add("is-collapsed");
                    r.classList.remove("is-expanded");
                } else {
                    r.classList.remove("is-collapsed");
                    r.classList.add("is-expanded");
                }
                applyChildrenVisibility(r, isCollapsing);
                saveTocFoldState();
            });
        });
    }

    function applyChildrenVisibility(row, hide) {
        var level = parseInt(row.getAttribute("data-level"), 10);
        var sibling = row.nextElementSibling;
        while (sibling) {
            var sLevel = parseInt(sibling.getAttribute("data-level"), 10);
            if (sLevel <= level) break;
            if (hide) {
                sibling.classList.add("is-hidden-by-collapse");
            } else {
                // Only show immediate children; deeper ones stay hidden if their own parent is collapsed
                if (sLevel === level + 1) {
                    sibling.classList.remove("is-hidden-by-collapse");
                }
            }
            sibling = sibling.nextElementSibling;
        }
    }

    function saveTocFoldState() {
        var collapsed = [];
        tocBody.querySelectorAll(".toc-row.is-collapsed").forEach(function (row) {
            collapsed.push(row.getAttribute("data-id"));
        });
        try { localStorage.setItem(TOC_FOLD_STORAGE, JSON.stringify(collapsed)); } catch (e) {}
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 4: Content heading toggle (individual)
    // ═══════════════════════════════════════════════════════════════
    function initContentFold() {
        getContentHeadings().forEach(function (heading) {
            if (heading.querySelector(".heading-toggle")) return;
            var toggle = document.createElement("button");
            toggle.className = "heading-toggle";
            toggle.textContent = "▼";
            toggle.title = "折叠/展开此章节";
            heading.insertBefore(toggle, heading.firstChild);
            toggle.addEventListener("click", function (e) {
                e.preventDefault(); e.stopPropagation();
                var h = this.closest("h1, h2, h3, h4, h5, h6");
                setContentHeadingCollapsed(h, !isContentHeadingCollapsed(h));
                saveExpandLevel();
            });
        });
        syncContentFoldControls();
    }

    function getContentUnder(heading, headingLevel) {
        var elements = [], sibling = heading.nextElementSibling;
        while (sibling) {
            var sibLevel = getHeadingLevel(sibling);
            if (sibLevel > 0 && sibLevel <= headingLevel) break;
            elements.push(sibling);
            sibling = sibling.nextElementSibling;
        }
        return elements;
    }

    var CONTENT_FOLD_CLASS = "is-hidden-by-content-fold";
    var collapsedContentHeadings = Object.create(null);

    function isContentHeadingCollapsed(heading) {
        return !!(heading && heading.id && collapsedContentHeadings[heading.id]);
    }

    function setContentHeadingCollapsed(heading, collapsed) {
        if (!heading || !heading.id) return;
        if (collapsed) collapsedContentHeadings[heading.id] = true;
        else delete collapsedContentHeadings[heading.id];
        applyContentFoldState();
    }

    function setContentHeadingToggle(heading, collapsed) {
        var toggle = heading.querySelector(".heading-toggle");
        if (!toggle) return;
        toggle.classList.toggle("collapsed", collapsed);
        toggle.textContent = collapsed ? "▶" : "▼";
    }

    function clearContentFoldClasses() {
        markdownBody.querySelectorAll("." + CONTENT_FOLD_CLASS).forEach(function (el) {
            el.classList.remove(CONTENT_FOLD_CLASS);
        });
    }

    function syncContentFoldControls() {
        getContentHeadings().forEach(function (heading) {
            setContentHeadingToggle(heading, isContentHeadingCollapsed(heading));
        });
    }

    function applyContentFoldState() {
        clearContentFoldClasses();
        getContentHeadings().forEach(function (heading) {
            if (!isContentHeadingCollapsed(heading)) return;
            getContentUnder(heading, getHeadingLevel(heading)).forEach(function (el) {
                el.classList.add(CONTENT_FOLD_CLASS);
            });
        });
        syncContentFoldControls();
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 5: Image Lightbox
    // ═══════════════════════════════════════════════════════════════
    function initImageLightbox() {
        markdownBody.addEventListener("click", function (event) {
            var img = event.target.closest("img");
            if (!img || img.closest(".lightbox-overlay")) return;
            var overlay = document.createElement("div");
            overlay.className = "lightbox-overlay";
            var largeImg = document.createElement("img");
            largeImg.src = img.src; largeImg.alt = img.alt || "";
            overlay.appendChild(largeImg);
            document.body.appendChild(overlay);
            overlay.addEventListener("click", function () { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); });
            largeImg.addEventListener("click", function (e) { e.stopPropagation(); if (overlay.parentNode) overlay.parentNode.removeChild(overlay); });
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 6: Code Copy
    // ═══════════════════════════════════════════════════════════════
    function initCodeCopy() {
        markdownBody.querySelectorAll("pre").forEach(function (pre) {
            if (pre.parentElement.classList.contains("code-block-wrapper")) return;
            var wrapper = document.createElement("div");
            wrapper.className = "code-block-wrapper";
            pre.parentNode.insertBefore(wrapper, pre);
            wrapper.appendChild(pre);
            var copyBtn = document.createElement("button");
            copyBtn.className = "copy-btn"; copyBtn.textContent = "复制";
            copyBtn.addEventListener("click", function (e) {
                e.preventDefault(); e.stopPropagation();
                var code = pre.textContent || "";
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(code).then(function () { copyBtn.textContent = "已复制"; setTimeout(function () { copyBtn.textContent = "复制"; }, 1500); })
                        .catch(function () { fallbackCopy(code, copyBtn); });
                } else { fallbackCopy(code, copyBtn); }
            });
            wrapper.appendChild(copyBtn);
        });
        function fallbackCopy(text, btn) {
            var textarea = document.createElement("textarea");
            textarea.value = text; textarea.style.position = "fixed"; textarea.style.left = "-9999px";
            document.body.appendChild(textarea); textarea.select();
            try { document.execCommand("copy"); btn.textContent = "已复制"; }
            catch (err) { btn.textContent = "失败"; }
            setTimeout(function () { btn.textContent = "复制"; }, 1500);
            document.body.removeChild(textarea);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 7: Table Horizontal Scroll
    // ═══════════════════════════════════════════════════════════════
    function initTableScroll() {
        markdownBody.querySelectorAll("table").forEach(function (table) {
            if (table.parentElement.classList.contains("table-wrapper")) return;
            var wrapper = document.createElement("div");
            wrapper.className = "table-wrapper";
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 8: Reading Position Restore
    // ═══════════════════════════════════════════════════════════════
    var scrollStorageKey = "mdviewer-scroll-" + (document.title || "document");
    function saveScrollPosition() { try { localStorage.setItem(scrollStorageKey, contentArea.scrollTop.toString()); } catch (e) {} }
    function restoreScrollPosition() {
        try { var saved = localStorage.getItem(scrollStorageKey); if (saved) { var pos = parseInt(saved, 10); if (pos > 0) { requestAnimationFrame(function () { requestAnimationFrame(function () { contentArea.scrollTop = pos; }); }); } } } catch (e) {}
    }
    function initPositionRestore() { window.addEventListener("beforeunload", saveScrollPosition); restoreScrollPosition(); }

    // ═══════════════════════════════════════════════════════════════
    // Module 9: Toolbar — step-wise content expand/collapse
    // ═══════════════════════════════════════════════════════════════
    function applyExpandLevel(level) {
        getContentHeadings().forEach(function (h) {
            if (!h.id) return;
            if (getHeadingLevel(h) > level) collapsedContentHeadings[h.id] = true;
            else delete collapsedContentHeadings[h.id];
        });
        applyContentFoldState();
    }

    function expandOneLevel() {
        if (currentExpandedLevel >= 6) {
            collapsedContentHeadings = Object.create(null);
            applyContentFoldState();
            saveExpandLevel();
            return;
        }
        currentExpandedLevel++;
        applyExpandLevel(currentExpandedLevel);
        saveExpandLevel();
    }

    function collapseOneLevel() {
        if (currentExpandedLevel <= 0) return;
        currentExpandedLevel--;
        applyExpandLevel(currentExpandedLevel);
        saveExpandLevel();
    }

    function saveExpandLevel() {
        try { localStorage.setItem(FOLD_STORAGE, String(currentExpandedLevel)); } catch (e) {}
    }

    function restoreExpandLevel() {
        var saved = null;
        try { saved = localStorage.getItem(FOLD_STORAGE); } catch (e) {}
        if (saved !== null) {
            currentExpandedLevel = parseInt(saved, 10);
            if (isNaN(currentExpandedLevel)) currentExpandedLevel = 6;
        }
        // default: all visible (level 6)
        if (currentExpandedLevel < 0) currentExpandedLevel = 6;
        if (currentExpandedLevel > 6) currentExpandedLevel = 6;
        applyExpandLevel(currentExpandedLevel);
    }

    // ═══════════════════════════════════════════════════════════════
    // TOC panel toggle (sidebar collapse to narrow strip)
    // ═══════════════════════════════════════════════════════════════
    var TOC_PANEL_STORAGE = "mdviewer-toc-panel-collapsed";
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

    // ═══════════════════════════════════════════════════════════════
    // Module 10: Dark Mode
    // ═══════════════════════════════════════════════════════════════
    var themeStorageKey = "mdviewer-theme";
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

    // ═══════════════════════════════════════════════════════════════
    // Module 11: Auto Numbering
    // ═══════════════════════════════════════════════════════════════
    var numberingStorageKey = "mdviewer-autonumbering";
    function markAlreadyNumberedHeadings() {
        getContentHeadings().forEach(function (h) {
            var text = "";
            for (var i = 0; i < h.childNodes.length; i++) {
                var node = h.childNodes[i];
                if (node.nodeType === 3) {
                    text += node.textContent;
                } else if (node.nodeType === 1) {
                    if (!node.classList.contains("heading-toggle")) {
                        text += node.textContent || "";
                    }
                }
            }
            if (/^\d+(\.\d+)*[\s\.、）\)　]/.test(text.trim()) || /^第[一二三四五六七八九十百千]+[章节]/.test(text.trim())) {
                h.classList.add("no-autonumber");
            }
        });
    }
    function applyAutoNumbering(enabled) {
        if (enabled) {
            document.documentElement.setAttribute("data-auto-numbering", "true");
        } else {
            document.documentElement.removeAttribute("data-auto-numbering");
        }
        var btn = document.getElementById("btn-auto-numbering");
        if (btn) btn.classList.toggle("active", enabled);
    }
    function initAutoNumbering() {
        var btn = document.getElementById("btn-auto-numbering"); if (!btn) return;
        markAlreadyNumberedHeadings();
        var saved = null; try { saved = localStorage.getItem(numberingStorageKey); } catch (e) {}
        applyAutoNumbering(saved === "true");
        btn.addEventListener("click", function () {
            var enabled = !document.documentElement.hasAttribute("data-auto-numbering");
            applyAutoNumbering(enabled);
            try { localStorage.setItem(numberingStorageKey, String(enabled)); } catch (ex) {}
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 12: TOC Resize
    // ═══════════════════════════════════════════════════════════════
    function initTocResize() {
        var resizer = document.getElementById("toc-resizer"); if (!resizer) return;
        try { var saved = localStorage.getItem("mdviewer-toc-width"); if (saved) { var w = parseInt(saved, 10); if (w >= 180 && w <= 500) document.documentElement.style.setProperty("--sidebar-width", w + "px"); } } catch (e) {}
        var startX, startWidth;
        resizer.addEventListener("mousedown", function (e) { e.preventDefault(); startX = e.clientX; startWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width")); document.body.classList.add("resizing"); resizer.classList.add("active"); window.addEventListener("mousemove", onMove); window.addEventListener("mouseup", onUp); });
        function onMove(e) { var w = Math.max(180, Math.min(500, startWidth + e.clientX - startX)); document.documentElement.style.setProperty("--sidebar-width", w + "px"); }
        function onUp() { document.body.classList.remove("resizing"); resizer.classList.remove("active"); window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); try { localStorage.setItem("mdviewer-toc-width", Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width"))).toString()); } catch (e) {} }
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 13: Back to Top
    // ═══════════════════════════════════════════════════════════════
    function initBackToTop() {
        var btn = document.getElementById("back-to-top-btn"); if (!btn) return;
        contentArea.addEventListener("scroll", function () { btn.classList.toggle("visible", contentArea.scrollTop > 300); });
        btn.addEventListener("click", function () { contentArea.scrollTo({ top: 0, behavior: "smooth" }); });
    }

    // ═══════════════════════════════════════════════════════════════
    // init — entry point
    // ═══════════════════════════════════════════════════════════════
    function init() {
        cacheDom();

        if (!tocBody || !contentArea || !markdownBody) {
            console.error("MDViewer init failed: required DOM nodes missing.");
            return;
        }

        restoreTocPanel();

        initTocClickJump();
        initScrollSpy();
        initTocFold();
        initContentFold();
        restoreExpandLevel();
        initImageLightbox();
        initCodeCopy();
        initTableScroll();
        initPositionRestore();
        initToolbar();
        initDarkMode();
        initAutoNumbering();
        initTocResize();
        initBackToTop();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

