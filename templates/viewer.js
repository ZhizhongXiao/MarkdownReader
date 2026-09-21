/* ================================================================
   MarkdownReader — Viewer JavaScript (shared across all templates)
   v4.0 — TOC panel toggle, fixed step-wise fold, auto-numbering fix
   ================================================================ */

(function () {
    "use strict";

    // Deferred DOM references — populated by cacheDom() inside init()
    var tocBody = null;
    var contentArea = null;
    var markdownBody = null;

    // ── Document state (v2) ──────────────────────────────────────────────
    // One canonical state per document, keyed by its path rather than its
    // title: two documents called README must never share reading state.
    //
    //   content.level      baseline: headings deeper than this are collapsed
    //   content.overrides  explicit user decisions, stored as the DIFFERENCE
    //                      from the baseline as it was at the moment of the
    //                      click
    //
    // Effective state of one heading:
    //   override present -> the override
    //   otherwise        -> getHeadingLevel(heading) > content.level
    //
    // Level changes only ever move the baseline; they never touch overrides,
    // not even when an override happens to agree with the new baseline.
    var DOC_STATE_PREFIX = "markdownreader-doc-state-v2:";
    var DOCUMENT_ID = window.location.pathname || "document";
    var DOCUMENT_STATE_KEY = DOC_STATE_PREFIX + DOCUMENT_ID;
    var MAX_EXPAND_LEVEL = 6;
    var documentState = {
        version: 2,
        content: { level: MAX_EXPAND_LEVEL, overrides: Object.create(null) }
    };
    // Legacy key of the previous single-level model. It is read only when a
    // document has no v2 state yet, is never modified, and keeps seeding every
    // document that has not been opened since the migration.
    var FOLD_STORAGE = "markdownreader-expandlevel";

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
            if (!targetElement) return;
            event.preventDefault();
            // Explicit navigation may unfold whatever hides its target; that is
            // a deliberate intent and is recorded as an explicit override.
            expandContentAncestorsForNavigation(targetElement);
            targetElement.scrollIntoView({ behavior: "smooth" });
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 2: Scroll Spy — Flat TOC
    // ═══════════════════════════════════════════════════════════════
    function initScrollSpy() {
        var allRows = tocBody.querySelectorAll(".toc-row");
        // Passive observation must not change what the user folded: this only
        // projects the active marker. When the target sits inside a branch the
        // user collapsed, the marker moves to the nearest VISIBLE ancestor, so
        // the reading position stays visible without touching any fold state.
        function nearestVisibleAncestorRow(row) {
            var level = parseInt(row.getAttribute("data-level"), 10);
            var node = row.previousElementSibling;
            while (node) {
                var nodeLevel = parseInt(node.getAttribute("data-level"), 10);
                if (nodeLevel < level) {
                    if (!node.classList.contains("is-hidden-by-collapse")) return node;
                    level = nodeLevel;
                }
                node = node.previousElementSibling;
            }
            return null;
        }

        function activateTocRow(id) {
            allRows.forEach(function (row) { row.classList.remove("active"); });
            var target = tocBody.querySelector('.toc-row[data-id="' + id + '"]');
            if (!target) return;
            var marked = target;
            if (target.classList.contains("is-hidden-by-collapse")) {
                marked = nearestVisibleAncestorRow(target);
                if (!marked) return;
            }
            marked.classList.add("active");
            marked.scrollIntoView({ block: "nearest", behavior: "smooth" });
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
    var TOC_FOLD_STORAGE = "markdownreader-toc-collapsed-v2";
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
                saveDocumentState();
            });
        });
        syncContentFoldControls();
    }

    var CONTENT_FOLD_CLASS = "is-hidden-by-content-fold";

    function isContentHeadingCollapsed(heading) {
        if (!heading || !heading.id) return false;
        var override = documentState.content.overrides[heading.id];
        if (override === "collapsed") return true;
        if (override === "expanded") return false;
        return getHeadingLevel(heading) > documentState.content.level;
    }

    function setContentHeadingCollapsed(heading, collapsed) {
        if (!heading || !heading.id) return;
        // An override records the difference from the baseline of this moment,
        // so returning to that baseline removes the entry again and the state
        // cannot accumulate entries that no longer mean anything.
        //
        // Only a manual click reaches this function. Level changes deliberately
        // never prune: the baseline can move across an override, and dropping it
        // at that point would silently discard a decision the user made.
        var baselineCollapsed = getHeadingLevel(heading) > documentState.content.level;
        if (collapsed === baselineCollapsed) delete documentState.content.overrides[heading.id];
        else documentState.content.overrides[heading.id] = collapsed ? "collapsed" : "expanded";
        applyContentFoldState();
    }

    // Content ancestors of a heading, outermost first, using the flat sibling
    // layout the fold model already relies on.
    function getContentAncestors(target) {
        var ancestors = [];
        var level = getHeadingLevel(target);
        var node = target.previousElementSibling;
        while (node && level > 1) {
            var nodeLevel = getHeadingLevel(node);
            if (nodeLevel > 0 && nodeLevel < level) {
                ancestors.unshift(node);
                level = nodeLevel;
            }
            node = node.previousElementSibling;
        }
        return ancestors;
    }

    // Explicit navigation (a TOC click) may unfold the collapsed ancestors that
    // hide its target. This deliberately does NOT go through the manual setter:
    // that one prunes an override matching the current baseline, which would
    // discard the navigation intent and let a later level change hide the
    // target again. The batch is written with one reconcile and one save, so the
    // existing clear-and-rebuild cost is not multiplied per ancestor.
    function expandContentAncestorsForNavigation(target) {
        var changed = false;
        getContentAncestors(target).forEach(function (ancestor) {
            if (!ancestor.id) return;
            if (!isContentHeadingCollapsed(ancestor)) return;
            documentState.content.overrides[ancestor.id] = "expanded";
            changed = true;
        });
        if (!changed) return;
        applyContentFoldState();
        saveDocumentState();
    }

    function setContentHeadingToggle(heading, collapsed) {
        var toggle = heading.querySelector(".heading-toggle");
        if (!toggle) return;
        toggle.classList.toggle("collapsed", collapsed);
        toggle.textContent = collapsed ? "▶" : "▼";
    }

    function syncContentFoldControls() {
        getContentHeadings().forEach(function (heading) {
            setContentHeadingToggle(heading, isContentHeadingCollapsed(heading));
        });
    }

    // One linear pass decides visibility, and the DOM is only touched where the
    // decision differs from what is already there. The previous version cleared
    // every hidden class and then rebuilt them, which produced a two-phase state
    // (a visible flicker) and rewrote classes that had not changed at all.
    function applyContentFoldState() {
        var hidden = new Set();
        var collapsedDepth = 0;
        var children = markdownBody.children;
        for (var i = 0; i < children.length; i++) {
            var element = children[i];
            var level = getHeadingLevel(element);
            if (level && collapsedDepth && level <= collapsedDepth) collapsedDepth = 0;
            if (collapsedDepth) hidden.add(element);
            if (level && !collapsedDepth && isContentHeadingCollapsed(element)) {
                collapsedDepth = level;
            }
        }
        hidden.forEach(function (element) {
            if (!element.classList.contains(CONTENT_FOLD_CLASS)) {
                element.classList.add(CONTENT_FOLD_CLASS);
            }
        });
        markdownBody.querySelectorAll("." + CONTENT_FOLD_CLASS).forEach(function (element) {
            if (hidden.has(element) || isInsideHiddenSection(element, hidden)) return;
            element.classList.remove(CONTENT_FOLD_CLASS);
        });
        syncContentFoldControls();
    }

    // A nested element - the table or code block a wrapper was built around after
    // the fold had already been applied - may keep its own class while its section
    // stays hidden, but it must not keep it once that section is revealed again.
    function isInsideHiddenSection(element, hidden) {
        var node = element.parentElement;
        while (node && node !== markdownBody) {
            if (hidden.has(node)) return true;
            node = node.parentElement;
        }
        return false;
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
    // The reading position belongs to the same document identity as the fold
    // state, so two documents with the same title cannot share it.
    var scrollStorageKey = "markdownreader-scroll-" + DOCUMENT_ID;
    var SCROLL_SAVE_DELAY = 250;

    // The stylesheet gives .content-area scroll-behavior:smooth, so restoring
    // the saved position is an ANIMATION: it emits a stream of scroll events
    // and its live value is a frame of that animation. Persisting those frames
    // would let the viewer overwrite a correct position with its own restore -
    // and if the page were closed mid-animation, the beforeunload fallback
    // would make that wrong value permanent. Hence a restore window: while it
    // is open, scroll events are not reading progress and the fallback saves the
    // restore TARGET instead of the live value.
    var RESTORE_WINDOW_TIMEOUT = 1500;
    var restoringPosition = false;
    var restoreTarget = 0;
    var restoreTimer = null;
    var saveTimer = null;

    function persistScrollPosition(position) {
        try { localStorage.setItem(scrollStorageKey, String(position)); } catch (e) {}
    }

    function saveScrollPosition() {
        persistScrollPosition(restoringPosition ? restoreTarget : contentArea.scrollTop);
    }

    function endRestoreWindow() {
        if (!restoringPosition) return;
        restoringPosition = false;
        restoreTarget = 0;
        if (restoreTimer !== null) { clearTimeout(restoreTimer); restoreTimer = null; }
        contentArea.removeEventListener("scrollend", endRestoreWindow);
        window.removeEventListener("wheel", endRestoreWindow, true);
        window.removeEventListener("touchstart", endRestoreWindow, true);
        window.removeEventListener("pointerdown", endRestoreWindow, true);
        window.removeEventListener("keydown", endRestoreWindow, true);
    }

    function beginRestoreWindow(target) {
        restoringPosition = true;
        restoreTarget = target;
        // scrollend is the accurate end-of-animation signal in Chromium; the
        // timeout covers environments that never fire it (jsdom among them). A
        // user gesture ends the window at once, so genuine reading during a long
        // restore is still recorded.
        contentArea.addEventListener("scrollend", endRestoreWindow);
        window.addEventListener("wheel", endRestoreWindow, true);
        window.addEventListener("touchstart", endRestoreWindow, true);
        window.addEventListener("pointerdown", endRestoreWindow, true);
        window.addEventListener("keydown", endRestoreWindow, true);
        restoreTimer = setTimeout(endRestoreWindow, RESTORE_WINDOW_TIMEOUT);
    }

    function onContentScroll() {
        if (restoringPosition) return;
        if (saveTimer !== null) return;
        saveTimer = setTimeout(function () {
            saveTimer = null;
            saveScrollPosition();
        }, SCROLL_SAVE_DELAY);
    }

    function restoreScrollPosition() {
        var saved = null;
        try { saved = localStorage.getItem(scrollStorageKey); } catch (e) {}
        var position = saved === null ? NaN : parseInt(saved, 10);
        if (!isFinite(position) || position <= 0) return;
        beginRestoreWindow(position);
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                contentArea.scrollTop = position;
            });
        });
    }

    function initPositionRestore() {
        contentArea.addEventListener("scroll", onContentScroll);
        // pagehide is the reliable hard stop (tab close, navigation, mobile
        // backgrounding); beforeunload stays as the last resort.
        window.addEventListener("pagehide", saveScrollPosition);
        window.addEventListener("beforeunload", saveScrollPosition);
        restoreScrollPosition();
    }

    // ═══════════════════════════════════════════════════════════════
    // Module 9: Toolbar — step-wise content expand/collapse
    // ═══════════════════════════════════════════════════════════════
    // Step-wise level control. This moves the baseline and nothing else: the
    // manual overrides survive, which is what stops a click here from restoring
    // a fold the user deliberately made. At the top of the range it is a no-op
    // rather than a wipe, so the button can never outrank an explicit decision.
    function expandOneLevel() {
        if (documentState.content.level >= MAX_EXPAND_LEVEL) return;
        documentState.content.level++;
        applyContentFoldState();
        saveDocumentState();
    }

    function collapseOneLevel() {
        if (documentState.content.level <= 0) return;
        documentState.content.level--;
        applyContentFoldState();
        saveDocumentState();
    }

    function saveDocumentState() {
        // Persist the whole state object rather than a rebuilt version/content
        // pair: fields this stage does not own yet (toc, scroll) must survive a
        // save instead of being dropped on the floor.
        try { localStorage.setItem(DOCUMENT_STATE_KEY, JSON.stringify(documentState)); } catch (e) {}
    }

    function parseStoredLevel(raw) {
        // The previous model only ever wrote String(currentExpandedLevel), so
        // anything that is not an integer is damage. Damage restores the default
        // instead of being guessed at: parseInt would read "3abc" as level 3.
        if (raw === null || String(raw).trim() === "") return MAX_EXPAND_LEVEL;
        var level = Number(raw);
        if (!Number.isInteger(level)) return MAX_EXPAND_LEVEL;
        return Math.max(0, Math.min(MAX_EXPAND_LEVEL, level));
    }

    function pruneOverrides() {
        // Heading ids that no longer exist cannot mean anything. They are
        // filtered in memory only: merely opening a document must not rewrite
        // its stored state. The next real save writes the filtered version.
        var existing = Object.create(null);
        getContentHeadings().forEach(function (h) {
            if (h.id) existing[h.id] = true;
        });
        Object.keys(documentState.content.overrides).forEach(function (id) {
            if (!existing[id]) delete documentState.content.overrides[id];
        });
    }

    function loadDocumentState() {
        var raw = null;
        try { raw = localStorage.getItem(DOCUMENT_STATE_KEY); } catch (e) {}

        var stored = null;
        if (raw) {
            try { stored = JSON.parse(raw); } catch (e) { stored = null; }
        }

        if (stored && typeof stored === "object" && stored.content
            && typeof stored.content === "object") {
            // Adopt the stored state, carrying fields this stage does not own
            // (toc, scroll) along so a later stage can take them over without a
            // migration. Nothing is written back here.
            documentState = stored;
            documentState.content.level = parseStoredLevel(documentState.content.level);
            if (!documentState.content.overrides
                || typeof documentState.content.overrides !== "object") {
                documentState.content.overrides = Object.create(null);
            }
            pruneOverrides();
        } else {
            // No v2 state for this document yet: seed from the legacy level and
            // persist right away, so the migration is observable. The legacy key
            // is never modified: it is global, so it must keep seeding every
            // document that has not been opened since the migration.
            var legacy = null;
            try { legacy = localStorage.getItem(FOLD_STORAGE); } catch (e) {}
            documentState = {
                version: 2,
                content: { level: parseStoredLevel(legacy), overrides: Object.create(null) }
            };
            pruneOverrides();
            saveDocumentState();
        }

        applyContentFoldState();
    }

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

    // ═══════════════════════════════════════════════════════════════
    // Module 11: Auto Numbering
    // ═══════════════════════════════════════════════════════════════
    var numberingStorageKey = "markdownreader-autonumbering";
    // Number recognition belongs to the converter: core/toc.py decides once and
    // publishes the result as data-explicit-number on every TOC row. The viewer
    // only consumes that conclusion, so there is no second definition of what an
    // explicit number looks like.
    function markAlreadyNumberedHeadings() {
        tocBody.querySelectorAll('.toc-row[data-explicit-number="true"]')
            .forEach(function (row) {
                var heading = document.getElementById(row.getAttribute("data-id"));
                if (heading) heading.classList.add("no-autonumber");
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
        try { var saved = localStorage.getItem("markdownreader-toc-width"); if (saved) { var w = parseInt(saved, 10); if (w >= 180 && w <= 500) document.documentElement.style.setProperty("--sidebar-width", w + "px"); } } catch (e) {}
        var startX, startWidth;
        resizer.addEventListener("mousedown", function (e) { e.preventDefault(); startX = e.clientX; startWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width")); document.body.classList.add("resizing"); resizer.classList.add("active"); window.addEventListener("mousemove", onMove); window.addEventListener("mouseup", onUp); });
        function onMove(e) { var w = Math.max(180, Math.min(500, startWidth + e.clientX - startX)); document.documentElement.style.setProperty("--sidebar-width", w + "px"); }
        function onUp() { document.body.classList.remove("resizing"); resizer.classList.remove("active"); window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); try { localStorage.setItem("markdownreader-toc-width", Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width"))).toString()); } catch (e) {} }
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
            console.error("MarkdownReader init failed: required DOM nodes missing.");
            return;
        }

        restoreTocPanel();

        initTocClickJump();
        initScrollSpy();
        initTocFold();
        initContentFold();
        loadDocumentState();
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

