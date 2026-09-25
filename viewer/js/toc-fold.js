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

