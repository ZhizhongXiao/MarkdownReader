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

