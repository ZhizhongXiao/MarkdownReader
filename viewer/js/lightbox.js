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
            var zoom = 1;
            overlay.appendChild(largeImg);
            document.body.appendChild(overlay);
            overlay.addEventListener("click", function () { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); });
            largeImg.addEventListener("click", function (e) { e.stopPropagation(); if (overlay.parentNode) overlay.parentNode.removeChild(overlay); });
            // The wheel zooms the image in place: the overlay itself never moves, so
            // the click that closes it keeps working at any zoom level.
            overlay.addEventListener("wheel", function (wheelEvent) {
                wheelEvent.preventDefault();
                var factor = wheelEvent.deltaY < 0 ? LIGHTBOX_ZOOM_STEP : 1 / LIGHTBOX_ZOOM_STEP;
                zoom = Math.min(LIGHTBOX_MAX_ZOOM, Math.max(1, zoom * factor));
                largeImg.style.transform = zoom === 1 ? "" : "scale(" + zoom + ")";
            }, { passive: false });
        });
    }

