    // ═══════════════════════════════════════════════════════════════
    // Module 9: Toolbar — step-wise content expand/collapse
    // ═══════════════════════════════════════════════════════════════
    // Step-wise level control. This moves the baseline and nothing else: the
    // manual overrides survive, which is what stops a click here from restoring
    // a fold the user deliberately made. At the top of the range it is a no-op
    // rather than a wipe, so the button can never outrank an explicit decision.
    function expandOneLevel() {
        if (documentState.content.level >= MAX_EXPAND_LEVEL) return;
        documentState.content.level++;
        applyContentFoldState();
        saveDocumentState();
    }

    function collapseOneLevel() {
        if (documentState.content.level <= 0) return;
        documentState.content.level--;
        applyContentFoldState();
        saveDocumentState();
    }

    function saveDocumentState() {
        // Persist the whole state object rather than a rebuilt version/content
        // pair: fields this stage does not own yet (toc, scroll) must survive a
        // save instead of being dropped on the floor.
        try { localStorage.setItem(DOCUMENT_STATE_KEY, JSON.stringify(documentState)); } catch (e) {}
    }

    function parseStoredLevel(raw) {
        // The previous model only ever wrote String(currentExpandedLevel), so
        // anything that is not an integer is damage. Damage restores the default
        // instead of being guessed at: parseInt would read "3abc" as level 3.
        if (raw === null || String(raw).trim() === "") return MAX_EXPAND_LEVEL;
        var level = Number(raw);
        if (!Number.isInteger(level)) return MAX_EXPAND_LEVEL;
        return Math.max(0, Math.min(MAX_EXPAND_LEVEL, level));
    }

    function pruneOverrides() {
        // Heading ids that no longer exist cannot mean anything. They are
        // filtered in memory only: merely opening a document must not rewrite
        // its stored state. The next real save writes the filtered version.
        var existing = Object.create(null);
        getContentHeadings().forEach(function (h) {
            if (h.id) existing[h.id] = true;
        });
        Object.keys(documentState.content.overrides).forEach(function (id) {
            if (!existing[id]) delete documentState.content.overrides[id];
        });
    }

    function loadDocumentState() {
        var raw = null;
        try { raw = localStorage.getItem(DOCUMENT_STATE_KEY); } catch (e) {}

        var stored = null;
        if (raw) {
            try { stored = JSON.parse(raw); } catch (e) { stored = null; }
        }

        if (stored && typeof stored === "object" && stored.content
            && typeof stored.content === "object") {
            // Adopt the stored state, carrying fields this stage does not own
            // (toc, scroll) along so a later stage can take them over without a
            // migration. Nothing is written back here.
            documentState = stored;
            documentState.content.level = parseStoredLevel(documentState.content.level);
            if (!documentState.content.overrides
                || typeof documentState.content.overrides !== "object") {
                documentState.content.overrides = Object.create(null);
            }
            pruneOverrides();
        } else {
            // No v2 state for this document yet: seed from the legacy level and
            // persist right away, so the migration is observable. The legacy key
            // is never modified: it is global, so it must keep seeding every
            // document that has not been opened since the migration.
            var legacy = null;
            try { legacy = localStorage.getItem(FOLD_STORAGE); } catch (e) {}
            documentState = {
                version: 2,
                content: { level: parseStoredLevel(legacy), overrides: Object.create(null) }
            };
            pruneOverrides();
            saveDocumentState();
        }

        applyContentFoldState();
    }

