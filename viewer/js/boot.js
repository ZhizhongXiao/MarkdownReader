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
        initThemeSwitcher();
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

