// Stage 6.7a - index page behaviour contracts (Stage 6 design, section 6.7).
//
// Every contract declares what it means TODAY:
//   "pass"  - must already hold; guards the fixed behaviour against regression
//   "xfail" - known-broken and locked now; STRICT: if it starts passing the
//             suite fails and the marker must be flipped to "pass", exactly like
//             the pytest xfail(strict=True) contracts used in stages 3-5.
//
// The contracts drive the REAL generated index page: the Python caller runs
// core/index_builder.build_index and hands this suite the page it produced plus
// the real templates/index/index.js. Nothing here greps the page source, and
// nothing here accepts a hand-written stub page.
//
// IX0 is the liveness sentinel: nothing else is trustworthy until the real page
// has proved that it initialised, that its toggle works and that its search
// filters. A contract that could pass on a page where the script never ran would
// be the Stage 5 false-guardrail mistake all over again.

import test from "node:test";
import assert from "node:assert/strict";

import { boot } from "./index_harness.mjs";

// Reporting contract: one synchronous line per contract, emitted while that test
// is still running. The Python caller counts those lines rather than trusting a
// summary printed at process exit, so a truncated or crashed run shows up as a
// missing record instead of a smaller green suite.
function contract(name, expectation, body) {
  test(name, async (t) => {
    let failure = null;
    try {
      await body(t);
    } catch (error) {
      failure = error;
    }

    const status = expectation === "xfail"
      ? (failure ? "xfail" : "xpass")
      : (failure ? "fail" : "pass");

    console.log("CONTRACT " + status + " " + name);
    if (status === "xfail") {
      t.diagnostic("xfail (expected): " + String(failure.message || failure).split("\n")[0]);
      return;
    }
    if (status === "xpass") {
      throw new Error('XPASS: contract now holds - flip its marker to "pass"');
    }
    if (status === "fail") {
      throw failure;
    }
  });
}

// The folder the fixture puts two documents in; the other group holds one.
const FOLDER = "甲组";
const OTHER_FOLDER = "乙组";

// ── IX0: liveness. Nothing else is trustworthy until this holds. ───────────
contract("IX0 liveness: the real generated index page is alive", "pass", async () => {
  const session = await boot();
  try {
    // The page under test really is the builder's output, node by node.
    assert.ok(session.element("#document-search"), "the generated page must carry the search box");
    assert.ok(session.element("#no-results"), "the generated page must carry the no-results note");
    assert.ok(session.element(".root-list .document-row"), "the root document must be listed");
    const folder = session.group(FOLDER);
    assert.ok(folder, "the folder group must exist");
    assert.ok(session.toggleOf(folder), "the folder group must carry its toggle");
    assert.ok(session.copyButtonOf(folder), "the folder group must carry its copy button");
    assert.ok(session.listOf(folder), "the folder group must carry its list");
    assert.ok(session.indexDirectory(), "the page must be served from a real directory path");

    // The generated page inlines the script this suite evaluates, so the harness
    // cannot silently end up testing a different file than the one that ships.
    assert.ok(session.inlinesSource(),
      "the generated page must inline templates/index/index.js verbatim");

    assert.equal(session.initError(), null,
      "initialising the real page must not throw: " + session.errorSummary());
    assert.deepEqual(session.errors(), [],
      "initialising the real page must not report an uncaught error");

    // The toggle really toggles, in both directions.
    const toggle = session.toggleOf(folder);
    const list = session.listOf(folder);
    assert.equal(session.isHidden(list), false, "precondition: the folder starts expanded");
    assert.equal(toggle.getAttribute("aria-expanded"), "true", "precondition: and says so");

    session.click(toggle);
    assert.equal(session.isHidden(list), true, "clicking the toggle must collapse the list");
    assert.equal(toggle.getAttribute("aria-expanded"), "false", "and the toggle must say so");

    session.click(toggle);
    assert.equal(session.isHidden(list), false, "clicking it again must expand the list");
    assert.equal(toggle.getAttribute("aria-expanded"), "true", "and the toggle must say so again");

    // The search really filters, in the folder section and in the root section.
    const search = session.element("#document-search");
    const noResults = session.element("#no-results");
    const root = session.element(".root-list");
    const other = session.group(OTHER_FOLDER);
    assert.ok(root && other, "precondition: both sections exist");

    session.type(search, "甲组一");
    assert.equal(session.visibleRows(folder).length, 1, "exactly one row of the group matches");
    assert.equal(session.visibleRows(other).length, 0, "the other group has no match");
    assert.equal(session.isHidden(other), true, "a group with no match must disappear");
    assert.equal(session.visibleRows(root).length, 0, "the root section has no match here");
    assert.equal(session.isHidden(noResults), true, "something matched, so the note stays away");

    session.type(search, "根文档");
    assert.equal(session.visibleRows(root).length, 1, "the root document must be findable");
    assert.equal(session.visibleRows(folder).length, 0, "the folder rows must be hidden again");

    session.type(search, "没有这个词");
    assert.equal(session.visibleRows(root).length, 0, "nothing may stay visible");
    assert.equal(session.isHidden(noResults), false, "no match at all must show the note");
  } finally { session.close(); }
});

// ── IX1 (I1): a copy that did not happen must not be reported as success. ──
// One contract, three sessions, so the record count stays at three:
//   A  the clipboard resolves      - the primary path must still work, and must
//                                    still be the primary path
//   B  the clipboard rejects, the  - the fallback must still be a working path,
//      fallback succeeds             not something a fix is allowed to delete
//   C  the clipboard rejects, the  - I1 itself: execCommand reports that the copy
//      fallback returns false        did not happen, so the button may not claim
//                                    that it did
// C deliberately does not demand a particular failure UI. The only rule is that
// failure must not impersonate success.
contract("IX1 copy feedback: a copy that did not happen is not reported as success", "pass", async () => {
  // A: the primary path.
  const granted = await boot({ clipboard: "resolve", execCommand: true });
  try {
    const button = granted.copyButtonOf(granted.group(FOLDER));
    granted.click(button);
    await granted.settle(4);
    assert.equal(granted.claimsSuccess(button), true,
      "a copy the clipboard accepted must report success: "
      + JSON.stringify(granted.copyFeedback(button)));
    assert.equal(granted.clipboardCalls().length, 1, "the clipboard must have been asked exactly once");
    assert.equal(granted.clipboardCalls()[0], granted.folderPath(FOLDER),
      "and it must have been asked for the real folder path");
    assert.equal(granted.execCalls().length, 0, "a working clipboard must not fall back");
  } finally { granted.close(); }

  // B: the fallback still works.
  const fallback = await boot({ clipboard: "reject", execCommand: true });
  try {
    const button = fallback.copyButtonOf(fallback.group(FOLDER));
    fallback.click(button);
    await fallback.settle(4);
    assert.equal(fallback.clipboardCalls().length, 1, "precondition: the clipboard was asked and refused");
    assert.equal(fallback.execCalls().length, 1, "the fallback must have been attempted");
    assert.equal(fallback.claimsSuccess(button), true,
      "a fallback copy that succeeded must still report success: "
      + JSON.stringify(fallback.copyFeedback(button)));
  } finally { fallback.close(); }

  // C: I1. The fallback ran and reported failure.
  const denied = await boot({ clipboard: "reject", execCommand: false });
  try {
    const button = denied.copyButtonOf(denied.group(FOLDER));
    const expected = denied.folderPath(FOLDER);
    denied.click(button);
    await denied.settle(4);
    assert.equal(denied.clipboardCalls().length, 1, "precondition: the clipboard was asked and refused");
    assert.equal(denied.execCalls().length, 1, "the fallback must have been attempted");
    assert.equal(denied.execCalls()[0], "copy", "the fallback must ask for a copy");
    assert.equal(denied.clipboardCalls()[0], expected, "the clipboard was asked for the real folder path");
    assert.equal(denied.execTexts()[0], expected, "the fallback staged the same real folder path");
    assert.equal(denied.claimsSuccess(button), false,
      "a copy that did not happen must not be reported as success: "
      + JSON.stringify(denied.copyFeedback(button)));
  } finally { denied.close(); }
});

// ── IX2 (I2): a missing node must degrade its own feature, not the page. ────
// The index page is a generated artifact, so it has to survive a template drift
// or a locally incomplete DOM. Each variant removes one node and then checks two
// things: the page still initialises, and the features that do not depend on that
// node still work. "One node is missing" must not become "the script gave up":
// that is the state the page is in today, because a single null node throws out
// of the listener or aborts the whole initialisation.
//
// Out of scope on purpose: dataset.search, location.pathname, malformed URIs,
// clipboard permission UX and the copy handler's own group lookup.
contract("IX2 robustness: a missing node degrades its own feature only", "pass", async () => {
  // V1: the search box is gone. The toggle and a copy path which is known to
  // succeed must both keep working: a missing search box may only kill search.
  const noSearch = await boot({
    clipboard: "resolve",
    execCommand: false,
    mutate: function (document) {
      document.getElementById("document-search").remove();
    },
  });
  try {
    assert.equal(noSearch.initError(), null,
      "a missing search box must not abort initialisation: " + noSearch.errorSummary());
    assert.deepEqual(noSearch.errors(), [], "and it must not report an uncaught error");
    const folder = noSearch.group(FOLDER);
    noSearch.click(noSearch.toggleOf(folder));
    assert.equal(noSearch.isHidden(noSearch.listOf(folder)), true,
      "the toggle must still work without the search box");

    // The clipboard is stubbed to accept the write, so this is a positive
    // sentinel that holds whatever I1 does: a copy that really succeeded must
    // still report success even when the search box was never there.
    const copyButton = noSearch.copyButtonOf(folder);
    noSearch.click(copyButton);
    await noSearch.settle(4);
    assert.equal(noSearch.claimsSuccess(copyButton), true,
      "copy must still work without the search box: " + noSearch.errorSummary());
    assert.equal(noSearch.execCalls().length, 0,
      "a working primary clipboard must not fall back");

    assert.deepEqual(noSearch.errors(), [], "and none of them may throw while doing so");
  } finally { noSearch.close(); }

  // V2: the no-results note is gone. Search itself must keep working.
  const noNote = await boot({
    mutate: function (document) { document.getElementById("no-results").remove(); },
  });
  try {
    assert.equal(noNote.initError(), null,
      "a missing note must not abort initialisation: " + noNote.errorSummary());
    const folder = noNote.group(FOLDER);
    noNote.type(noNote.element("#document-search"), "甲组一");
    assert.equal(noNote.visibleRows(folder).length, 1, "search must still filter without the note");
    assert.equal(noNote.visibleRows(noNote.group(OTHER_FOLDER)).length, 0,
      "and it must still hide the rows that do not match");
    assert.deepEqual(noNote.errors(), [], "and it must not throw while doing so");
  } finally { noNote.close(); }

  // V3a: the toggle exists but the list it controls is gone.
  const noList = await boot({
    mutate: function (document) {
      document.querySelector('.folder-group[data-folder="' + FOLDER + '"] .document-list').remove();
    },
  });
  try {
    assert.equal(noList.initError(), null,
      "an incomplete group must not abort initialisation: " + noList.errorSummary());
    const folder = noList.group(FOLDER);
    noList.click(noList.toggleOf(folder));
    assert.deepEqual(noList.errors(), [], "a toggle without its list must not throw");
    noList.type(noList.element("#document-search"), "甲组一");
    assert.deepEqual(noList.errors(), [], "and a search hit on it must not throw either");
    assert.equal(noList.visibleRows(noList.group(OTHER_FOLDER)).length, 0,
      "the groups that are complete must still be filtered");
  } finally { noList.close(); }

  // V3b: a group the search will hit has no toggle.
  const noToggle = await boot({
    mutate: function (document) {
      document.querySelector('.folder-group[data-folder="' + FOLDER + '"] .folder-header .toggle-btn').remove();
    },
  });
  try {
    assert.equal(noToggle.initError(), null,
      "a missing toggle must not abort initialisation: " + noToggle.errorSummary());
    noToggle.type(noToggle.element("#document-search"), "甲组一");
    assert.deepEqual(noToggle.errors(), [], "a search hit on a group without a toggle must not throw");
    assert.equal(noToggle.visibleRows(noToggle.element(".root-list")).length, 0,
      "the filtering of the other sections must still happen");
  } finally { noToggle.close(); }
});

// ── IX3 (7.2): a copy button outside any folder group must no-op safely. ───
// The generated page always emits .copy-btn inside .folder-group, so this
// simulates template drift: one button ends up outside its group. The handler
// dereferenced the closest group without checking and threw out of the listener.
// The question here is deliberately narrow - that one click must do nothing, and
// the rest of the page must not notice.
contract("IX3 copy outside a folder group is a safe no-op", "pass", async () => {
  const session = await boot({
    clipboard: "resolve",
    execCommand: false,
    mutate: function (document) {
      const moved = document.querySelector('.folder-group[data-folder="' + FOLDER + '"] .copy-btn');
      moved.setAttribute("data-detached", "1");
      document.body.appendChild(moved);
    },
  });
  try {
    assert.equal(session.initError(), null,
      "moving a copy button must not abort initialisation: " + session.errorSummary());

    const detached = session.element("[data-detached]");
    assert.ok(detached, "precondition: the button was moved");
    assert.equal(detached.closest(".folder-group"), null,
      "precondition: it no longer belongs to a folder group");

    session.click(detached);
    await session.settle(4);

    // Without a group there is no folder path to copy at all, so the click must
    // not reach either copy channel - a fix that merely survives the throw but
    // still copies a bogus path would not be good enough.
    assert.equal(session.clipboardCalls().length, 0, "a button without a group must copy nothing");
    assert.equal(session.execCalls().length, 0, "and it must not fall back either");
    assert.equal(session.claimsSuccess(detached), false, "and it must not claim success");
    assert.deepEqual(session.errors(), [],
      "a button without a group must not throw: " + session.errorSummary());

    // An unrelated feature on the same page must still work.
    const folder = session.group(FOLDER);
    session.click(session.toggleOf(folder));
    assert.equal(session.isHidden(session.listOf(folder)), true,
      "the toggle must still collapse its list");
    assert.deepEqual(session.errors(), [], "and it must not throw while doing so");
  } finally { session.close(); }
});

// ── IX4 (7.3a): a row without data-search must not take the search down. ───
// The builder always emits data-search, so this is template drift again: the
// haystack is optional in the DOM but the filter required it.
contract("IX4 a row without data-search is treated as no match", "pass", async () => {
  const session = await boot({
    mutate: function (document) {
      document.querySelector('.folder-group[data-folder="' + FOLDER + '"] .document-row')
        .removeAttribute("data-search");
      document.querySelector(".root-list .document-row").removeAttribute("data-search");
    },
  });
  try {
    assert.equal(session.initError(), null,
      "a row without a haystack must not abort initialisation: " + session.errorSummary());

    const search = session.element("#document-search");
    const folder = session.group(FOLDER);
    const root = session.element(".root-list");
    const noResults = session.element("#no-results");

    // The query the stripped folder row would have matched before the mutation.
    session.type(search, "甲组一号");
    assert.deepEqual(session.errors(), [],
      "a missing haystack must not throw: " + session.errorSummary());
    assert.equal(session.visibleRows(folder).length, 0,
      "a row whose haystack is gone cannot claim a match");
    assert.equal(session.isHidden(noResults), false, "nothing matches, so the note is shown");

    // The empty query is the baseline: every row is visible and nothing is claimed.
    // It is also the sentinel that the filter is alive rather than dead.
    session.type(search, "");
    assert.equal(session.visibleRows(folder).length, 2, "clearing the query brings the rows back");
    assert.equal(session.visibleRows(root).length, 1, "including the root row");
    assert.deepEqual(session.errors(), [], "and nothing may throw on the way");
  } finally { session.close(); }
});

// ── IX5 (7.3a): a malformed escape in the page URL must not break copying. ──
// getIndexDirectory decodes location.pathname to derive the folder path, and
// decodeURIComponent throws a URIError on a malformed escape - inside the click
// listener, where it became an uncaught error.
contract("IX5 a malformed page URL does not break the copy button", "pass", async () => {
  const session = await boot({
    url: "http://localhost/C:/Docs/%ZZ/index.html",
    clipboard: "resolve",
    execCommand: false,
  });
  try {
    assert.equal(session.initError(), null,
      "a malformed URL must not abort initialisation: " + session.errorSummary());

    const button = session.copyButtonOf(session.group(FOLDER));
    session.click(button);
    await session.settle(4);

    assert.deepEqual(session.errors(), [],
      "clicking copy must not throw on a malformed URL: " + session.errorSummary());
    // Whatever the fallback decides to copy, it must be a real string: losing the
    // directory is a degraded answer, not a crash and not an undefined argument.
    assert.ok(session.clipboardCalls().length <= 1, "the copy is attempted at most once");
    session.clipboardCalls().forEach(function (value) {
      assert.equal(typeof value, "string", "the copy argument must stay a string");
    });
    assert.equal(session.claimsSuccess(button), session.clipboardCalls().length === 1,
      "success is claimed exactly when a copy was attempted and accepted");

    const folder = session.group(FOLDER);
    session.click(session.toggleOf(folder));
    assert.equal(session.isHidden(session.listOf(folder)), true, "the toggle must still collapse");
    assert.deepEqual(session.errors(), [], "and it must not throw while doing so");
  } finally { session.close(); }
});

// ── IX6 (7.3b): the copied Windows path is a product-level fact. ───────────
// IX1 already checks a copied path, but it derives the expectation with the
// harness folderPath helper, so a mistake shared by that helper and the page
// would cancel out. IX6 pins the literal results instead, for the two shapes the
// product can really produce: a page opened from a local file URL, in a normal
// directory and in a drive root.
//
// This is a regression lock, not a fix: both shapes are already correct, which is
// why the record starts as "pass". If it ever fails, the fixture and the real page
// have diverged and that divergence is the bug to chase.
contract("IX6 the copied folder path is the product path", "pass", async () => {
  // A: a normal, non-root directory. The folder name is percent-encoded on the
  // way in and decoded again by the page, so the escape round-trip is locked too.
  const deep = await boot({
    url: "file:///C:/文档/卡/index.html",
    clipboard: "resolve",
    execCommand: false,
  });
  try {
    const button = deep.copyButtonOf(deep.group("乙组"));
    deep.click(button);
    await deep.settle(4);
    assert.deepEqual(deep.clipboardCalls(), ["C:\\文档\\卡\\乙组"],
      "a folder in a normal directory must copy its absolute path");
    assert.equal(deep.execCalls().length, 0, "a working clipboard must not fall back");
    assert.equal(deep.claimsSuccess(button), true, "and the copy must be reported");
    assert.deepEqual(deep.errors(), [], "and nothing may throw: " + deep.errorSummary());
  } finally { deep.close(); }

  // B: the page itself sits in a drive root, where the intermediate directory is
  // just "C:". The composed path must still be a real path, with no doubled
  // separator and no bare drive letter.
  const root = await boot({
    url: "file:///C:/index.html",
    clipboard: "resolve",
    execCommand: false,
  });
  try {
    const button = root.copyButtonOf(root.group("乙组"));
    root.click(button);
    await root.settle(4);
    assert.deepEqual(root.clipboardCalls(), ["C:\\乙组"],
      "a drive root must not produce a doubled separator or a bare drive");
    assert.equal(root.execCalls().length, 0, "a working clipboard must not fall back");
    assert.equal(root.claimsSuccess(button), true, "and the copy must be reported");
    assert.deepEqual(root.errors(), [], "and nothing may throw: " + root.errorSummary());
  } finally { root.close(); }
});

// ── IX7 (7.5): a title the page shows must be findable by typing it. ───────
// The generator folds the haystack with Python casefold(), which is more
// aggressive than the browser lowercase the page applies to the query: Straße
// becomes strasse in the haystack while the typed query stays straße, so the
// document cannot be found by its own visible title.
//
// This locks that single invariant, not casefold-equivalent search: typing
// STRASSE is deliberately not required to match, because that would demand a
// Unicode folding implementation the browser does not have.
contract("IX7 a visible title stays searchable with the page normalization", "pass", async () => {
  const session = await boot();
  try {
    assert.equal(session.initError(), null,
      "the fixture page must initialise first: " + session.errorSummary());

    const group = session.group("德文组");
    assert.ok(group, "precondition: the fixture contains the German group");
    const row = group.querySelector(".document-row");
    assert.ok(row, "precondition: the group lists the document");

    const search = session.element("#document-search");
    session.type(search, "");
    assert.equal(row.hidden, false, "precondition: the row is visible with an empty query");

    session.type(search, "Straße");
    assert.equal(row.hidden, false,
      "typing the visible title must keep the row visible, so both sides normalise alike");
    assert.deepEqual(session.errors(), [],
      "and the search must not throw: " + session.errorSummary());

    session.type(search, "STRAẞE");
    assert.equal(row.hidden, false, "the upper-case spelling must match too");
    assert.deepEqual(session.errors(), [], "and it must not throw either");
  } finally { session.close(); }
});


