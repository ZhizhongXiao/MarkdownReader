    // ═══════════════════════════════════════════════════════════════
    // Module 13: Back to Top
    // ═══════════════════════════════════════════════════════════════
    function initBackToTop() {
        var btn = document.getElementById("back-to-top-btn"); if (!btn) return;
        contentArea.addEventListener("scroll", function () { btn.classList.toggle("visible", contentArea.scrollTop > 300); });
        btn.addEventListener("click", function () { contentArea.scrollTo({ top: 0, behavior: "smooth" }); });
    }

