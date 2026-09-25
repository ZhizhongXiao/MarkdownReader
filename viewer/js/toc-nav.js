
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

