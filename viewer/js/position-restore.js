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

