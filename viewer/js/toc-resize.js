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

