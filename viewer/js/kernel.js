/* ================================================================
   MarkdownReader — Viewer JavaScript (shared across all templates)
   v4.0 — TOC panel toggle, fixed step-wise fold, auto-numbering fix
   ================================================================ */

(function () {
    "use strict";

    // Deferred DOM references — populated by cacheDom() inside init()
    var tocBody = null;
    var contentArea = null;
    var markdownBody = null;

