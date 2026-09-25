    // ── Document state (v2) ──────────────────────────────────────────────
    // One canonical state per document, keyed by its path rather than its
    // title: two documents called README must never share reading state.
    //
    //   content.level      baseline: headings deeper than this are collapsed
    //   content.overrides  explicit user decisions, stored as the DIFFERENCE
    //                      from the baseline as it was at the moment of the
    //                      click
    //
    // Effective state of one heading:
    //   override present -> the override
    //   otherwise        -> getHeadingLevel(heading) > content.level
    //
    // Level changes only ever move the baseline; they never touch overrides,
    // not even when an override happens to agree with the new baseline.
    var DOC_STATE_PREFIX = "markdownreader-doc-state-v2:";
    var DOCUMENT_ID = window.location.pathname || "document";
    var DOCUMENT_STATE_KEY = DOC_STATE_PREFIX + DOCUMENT_ID;
    var MAX_EXPAND_LEVEL = 6;
    // The image lightbox zooms with the wheel, between the fitted size and this
    // factor: the whole image is already visible at 1, so shrinking has no use.
    var LIGHTBOX_MAX_ZOOM = 6;
    var LIGHTBOX_ZOOM_STEP = 1.15;
    var documentState = {
        version: 2,
        content: { level: MAX_EXPAND_LEVEL, overrides: Object.create(null) }
    };
    // Legacy key of the previous single-level model. It is read only when a
    // document has no v2 state yet, is never modified, and keeps seeding every
    // document that has not been opened since the migration.
    var FOLD_STORAGE = "markdownreader-expandlevel";

    function getHeadingLevel(el) {
        var tag = el.tagName.toUpperCase();
        if (tag.length === 2 && tag[0] === "H") return parseInt(tag[1], 10);
        return 0;
    }

    function getContentHeadings() {
        return markdownBody.querySelectorAll("h1[id], h2[id], h3[id], h4[id], h5[id], h6[id]");
    }

    // ═══════════════════════════════════════════════════════════════
    // cacheDom — must be called AFTER DOMContentLoaded
    // ═══════════════════════════════════════════════════════════════
    function cacheDom() {
        tocBody = document.getElementById("toc-body");
        contentArea = document.getElementById("content-area");
        markdownBody = document.getElementById("markdown-body");
    }
