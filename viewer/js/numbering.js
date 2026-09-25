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

