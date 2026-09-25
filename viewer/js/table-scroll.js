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

