// Stage 6.1a — viewer state contracts (Stage 6 design, section 6.1).
//
// Every contract declares what it means TODAY:
//   "pass"  — must already hold; guards the fixed behaviour against regression
//   "xfail" — known-broken and locked now; STRICT: if it starts passing the
//             suite fails and the marker must be flipped to "pass", exactly like
//             the pytest xfail(strict=True) contracts used in stages 3-5.
//
// The contracts are behavioural: they drive the real generated HTML through
// clicks, scrolls and fake intersection events, then read classes, storage and
// recorded calls. They never grep the viewer source.
//
// jsdom has no layout engine, so "the restored position got clamped" (V2)
// cannot be observed here. Those contracts assert ordering instead: the fold
// state must be complete on the DOM before the scroll position is written.

import test from "node:test";
import assert from "node:assert/strict";

import {
  boot,
  docStateOf,
  LEGACY_FOLD_KEY,
  DOC_STATE_PREFIX,
} from "./harness.mjs";

// Reporting contract: one synchronous line per contract, emitted while that
// test is still running.
//
// A summary emitted from an `after()` hook or a process.on("exit") handler is
// tempting but fragile in two ways: an ESM named import of `after` is resolved
// at module load, so it hard-fails on any Node version that does not export it
// (a `typeof` guard cannot run), and an exit handler cannot be relied on to
// flush stdout into a pipe. Per-test output is already the path the Python
// caller observes, and that caller counts the lines itself, so a truncated or
// crashed run becomes an explicit failure instead of a smaller green suite.
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

// Both fixtures are named README.md, so both documents share a title while
// living at different pathnames: the precondition for the D1 contract.
const TITLE = "README";
const SCROLL_KEY = "markdownreader-scroll-" + TITLE;

function pathnameOf(variant) {
  const url = process.env[variant === "B" ? "MR_FIXTURE_B_URL" : "MR_FIXTURE_A_URL"];
  return new URL(url).pathname;
}

function idsOf(elements) {
  return elements.map((element) => element.id || element.tagName).sort();
}

const ADVANCE = "btn-expand-all-content"; // 展开下一级
const COLLAPSE = "btn-collapse-all-content"; // 折叠上一级

const h = (session, prefix) => session.headingStartingWith(prefix);

// ── S0: liveness. Nothing else is trustworthy until this holds. ─────────────
contract("S0 liveness: the viewer really initialised on the fixture", "pass", async () => {
  const session = await boot();
  try {
    const sentinels = session.sentinels();
    assert.equal(sentinels.readyState, "complete");
    assert.deepEqual(sentinels.errors, [], "the viewer must not log init failures");
    assert.equal(sentinels.contentArea, true);
    assert.equal(sentinels.markdownBody, true);
    assert.equal(sentinels.headings, 12);
    assert.equal(sentinels.headingToggles, 12, "every body heading gets a fold toggle");
    assert.equal(sentinels.tableWrappers, 1, "the fixture table gets a scroll wrapper");
    assert.equal(sentinels.observed, 12, "every body heading is observed by the scroll spy");
    assert.equal(sentinels.tocRows, 12);
    assert.equal(sentinels.tocToggles, 7);
    assert.equal(session.doc.title, TITLE);
  } finally {
    session.close();
  }
});

// ── S1: ordering guard. The fold state must land before the scroll write. ───
contract("S1 ordering: the fold state is complete before the position is restored", "pass", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "3", [SCROLL_KEY]: "500" } });
  try {
    await session.frames(4);
    const write = session.scrollLog[0];
    assert.ok(write, "the saved position must be written back on load");
    assert.equal(write.value, 500);
    assert.equal(
      write.hiddenAtWrite,
      session.hiddenCount(),
      "the fold state must already be complete when scrollTop is written",
    );
    assert.ok(session.hiddenCount() > 0, "level 3 must hide something for this guard to be meaningful");
  } finally {
    session.close();
  }
});

// ── F1 (V8): a manual fold must survive a reload. ───────────────────────────
contract("F1 manual fold survives a reload", "xfail", async () => {
  const first = await boot({ seed: { [LEGACY_FOLD_KEY]: "2" } });
  let hiddenAfterToggle;
  let storage;
  try {
    const baseline = first.hiddenCount();
    first.clickHeadingToggle(h(first, "1.1 甲组"));
    hiddenAfterToggle = first.hiddenCount();
    storage = first.storage();
    assert.ok(
      hiddenAfterToggle > baseline,
      "precondition: the manual collapse must hide more than the baseline did",
    );
  } finally {
    first.close();
  }

  const reloaded = await boot({ seed: storage });
  try {
    assert.equal(
      reloaded.hiddenCount(),
      hiddenAfterToggle,
      "a manual collapse must still be in effect after a reload",
    );
  } finally {
    reloaded.close();
  }
});

// ── F2 (V1): a manual collapse must survive a level change. ─────────────────
contract("F2 manual collapse survives a level change", "xfail", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "3" } });
  try {
    // The discriminator must be the override's OWN effect, not a document
    // total: a level change legitimately changes how much the baseline hides,
    // so a global count cannot distinguish "the override was kept" from "the
    // baseline moved". This child stays hidden only while the manual collapse
    // survives, so it isolates the override.
    const child = h(session, "甲一子项");
    session.clickHeadingToggle(h(session, "1.1.1 甲一"));
    assert.equal(session.isHidden(child), true, "precondition: the manual collapse hid the child");

    session.clickToolbar(ADVANCE);

    assert.equal(
      session.isHidden(child),
      true,
      "the level buttons must not discard a manual collapse",
    );
  } finally {
    session.close();
  }
});

// ── F3 (V1): a manual expand must survive a level round trip. ───────────────
contract("F3 manual expand survives a level round trip", "xfail", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "3" } });
  try {
    const deepest = h(session, "乙一深项");
    assert.equal(session.isHidden(deepest), true, "precondition: level 3 hides the h5");
    session.clickHeadingToggle(h(session, "乙一子项"));
    assert.equal(session.isHidden(deepest), false, "precondition: the manual expand revealed the h5");
    session.clickToolbar(COLLAPSE);
    session.clickToolbar(ADVANCE);
    assert.equal(
      session.isHidden(deepest),
      false,
      "the level buttons must not discard a manual expand",
    );
  } finally {
    session.close();
  }
});

// ── F4: an override equal to the baseline is not worth storing. ─────────────
contract("F4 redundant overrides are pruned", "xfail", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "3" } });
  try {
    const heading = h(session, "丙一子项");
    session.clickHeadingToggle(heading); // manual expand ...
    session.clickHeadingToggle(heading); // ... then back to the baseline
    const state = docStateOf(session.storage(), pathnameOf("A"));
    assert.ok(state, "expected a v2 document state to be persisted");
    assert.deepEqual(state.content.overrides, {}, "no override may restate the baseline");
  } finally {
    session.close();
  }
});

// ── F5: state that references headings which no longer exist must be inert. ─
contract("F5 removed headings never break the stored state", "xfail", async () => {
  const stale = {
    version: 2,
    content: { level: 2, overrides: { "ghost-heading": "collapsed" } },
    toc: { collapsed: ["ghost-row"] },
    scroll: { top: 0 },
  };
  const session = await boot({
    seed: { [DOC_STATE_PREFIX + pathnameOf("A")]: JSON.stringify(stale) },
  });
  try {
    assert.equal(
      session.hiddenCount(),
      4,
      "the stored baseline must still apply when it mentions removed headings",
    );
    assert.deepEqual(session.errors, []);
  } finally {
    session.close();
  }
});

// ── M1: the legacy level value migrates into the v2 document state. ─────────
contract("M1 legacy level migrates into the v2 document state", "xfail", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "3" } });
  try {
    assert.equal(session.hiddenCount(), 1, "the legacy value must keep driving the baseline");
    const state = docStateOf(session.storage(), pathnameOf("A"));
    assert.ok(state, "the legacy value must be migrated, not merely read");
    assert.equal(state.content.level, 3);
    assert.deepEqual(state.content.overrides, {});
  } finally {
    session.close();
  }
});

// ── M2: V9 — a corrupt legacy value must not mean "expand everything". ──────
contract("M2 legacy level clamps on migration (-1 to 0, 7 to 6, NaN to 6)", "xfail", async () => {
  const cases = [["-1", 0], ["7", 6], ["not-a-number", 6]];
  for (const [raw, expected] of cases) {
    const session = await boot({ seed: { [LEGACY_FOLD_KEY]: raw } });
    try {
      const state = docStateOf(session.storage(), pathnameOf("A"));
      assert.ok(state, "expected migration for legacy value " + JSON.stringify(raw));
      assert.equal(state.content.level, expected, "legacy " + raw + " must clamp to " + expected);
    } finally {
      session.close();
    }
  }
});

// ── D1 (V6): document identity is the path, never the title. ────────────────
contract("D1 same title, different pathname: positions never leak", "xfail", async () => {
  const a = await boot({ variant: "A" });
  const b = await boot({ variant: "B" });
  let title;
  try {
    title = a.doc.title;
    assert.equal(title, b.doc.title, "precondition: both fixtures carry the same title");
    assert.notEqual(
      a.window.location.pathname,
      b.window.location.pathname,
      "precondition: their pathnames differ",
    );
  } finally {
    a.close();
    b.close();
  }

  const seed = { ["markdownreader-scroll-" + title]: "500" };

  const first = await boot({ variant: "A", seed });
  try {
    await first.frames(4);
    assert.deepEqual(
      first.scrollLog.map((entry) => entry.value),
      [500],
      "A must restore its own saved position",
    );
  } finally {
    first.close();
  }

  const second = await boot({ variant: "B", seed });
  try {
    await second.frames(4);
    assert.deepEqual(second.scrollLog, [], "B must not replay A's saved position");
  } finally {
    second.close();
  }
});

// ── S2 (V7): reading position is saved while reading, not only on unload. ───
contract("S2 scrolling is persisted without waiting for unload", "xfail", async () => {
  const session = await boot();
  try {
    session.scrollTo(120);
    session.scrollTo(240);
    await session.sleep(400);
    assert.ok(
      JSON.stringify(session.storage()).includes("240"),
      "the latest position must be written while reading",
    );
  } finally {
    session.close();
  }
});

// ── S2b (V7): pagehide is the hard-stop fallback. ───────────────────────────
contract("S2b pagehide forces a save", "xfail", async () => {
  const session = await boot();
  try {
    session.scrollTo(320);
    session.window.dispatchEvent(new session.window.Event("pagehide"));
    assert.ok(
      JSON.stringify(session.storage()).includes("320"),
      "pagehide must force a save so a hard kill still keeps the position",
    );
  } finally {
    session.close();
  }
});

// ── T1 (V3): a passive observer must never change user TOC folds. ───────────
contract("T1 the scroll spy never changes user-collapsed TOC branches", "xfail", async () => {
  const session = await boot();
  try {
    const branch = h(session, "1.1 甲组");
    session.clickTocToggle(branch.id);
    const collapsedBefore = session.tocCollapsedIds();
    const hiddenBefore = session.tocHiddenIds();
    assert.ok(collapsedBefore.includes(branch.id), "precondition: the branch is user-collapsed");
    assert.ok(hiddenBefore.length > 0, "precondition: the branch hides rows");

    const fired = session.fireSpy(h(session, "乙一深项").id);
    assert.equal(fired, 1, "precondition: the spy received an intersection event");

    assert.deepEqual(session.tocCollapsedIds(), collapsedBefore,
      "the spy must not clear a user-collapsed row");
    assert.deepEqual(session.tocHiddenIds(), hiddenBefore,
      "the spy must not reveal a user-collapsed branch");
  } finally {
    session.close();
  }
});

// ── T2 (V3): the active marker must not hijack a collapsed branch. ──────────
contract("T2 the active heading is indicated without expanding its branch", "xfail", async () => {
  const session = await boot();
  try {
    const branch = h(session, "1.1 甲组");
    session.clickTocToggle(branch.id);
    session.fireSpy(h(session, "一、乙组").id);
    const row = session.tocRow(branch.id);
    assert.ok(
      row.classList.contains("active") || row.classList.contains("contains-active"),
      "the nearest visible ancestor of the active heading must be marked",
    );
    assert.deepEqual(session.tocCollapsedIds(), [branch.id],
      "and that branch must stay collapsed");
  } finally {
    session.close();
  }
});

// ── N1 (V4): explicit navigation may unfold whatever blocks the jump. ───────
contract("N1 TOC navigation unfolds a target hidden by the content fold", "xfail", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "2" } });
  try {
    session.clickHeadingToggle(h(session, "1.1 甲组"));
    const target = h(session, "一、乙组");
    assert.equal(session.isHidden(target), true, "precondition: the target is folded away");
    session.spy.scrollIntoView.length = 0;

    session.clickTocLink(target.id);

    assert.equal(session.isHidden(target), false,
      "clicking a TOC entry for a hidden heading must unfold its ancestors first");
    assert.ok(session.spy.scrollIntoView.some((call) => call.id === target.id),
      "the jump itself must still happen");
  } finally {
    session.close();
  }
});

// ── N2 (V4): the unfolding that navigation caused must be persisted. ────────
contract("N2 navigation-induced unfolding is persisted as an override", "xfail", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "2" } });
  let storage;
  let branchId;
  try {
    const branch = h(session, "1.1 甲组");
    branchId = branch.id;
    session.clickHeadingToggle(branch);
    session.clickTocLink(h(session, "一、乙组").id);
    storage = session.storage();
  } finally {
    session.close();
  }

  const state = docStateOf(storage, pathnameOf("A"));
  assert.ok(state, "expected a v2 document state");
  assert.equal(state.content.overrides[branchId], "expanded",
    "navigation must record an expanded override for every ancestor it unfolded");
});

// ── P1 (V5): no clear-then-rebuild pass over the whole document. ────────────
// The observed toggle COLLAPSES a section, so the only legitimate class changes
// are additions: a removal can then only come from "clear everything, recompute
// everything". This is the one contract that observes an operation pattern
// rather than resulting state, because in a layout-less environment the
// symptom (flicker) is unobservable.
contract("P1 collapsing a section never clears the hidden class elsewhere", "xfail", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "2" } });
  try {
    const before = session.hiddenCount();
    assert.ok(before > 0, "precondition: the baseline hides something");

    const operations = await session.hiddenClassOperations(() => {
      session.clickHeadingToggle(h(session, "1.1 甲组"));
    });

    assert.ok(session.hiddenCount() > before, "precondition: the toggle hid more than before");
    assert.equal(operations.removes, 0,
      "collapsing must not strip the hidden class from elements that stay hidden");
  } finally {
    session.close();
  }
});

// ── NUM1 (V10): Python owns number recognition; the viewer rejects the rest. ─
// "2）楔子" is NOT an explicit number for core/toc.py, but the viewer's own
// regex matches it, so it currently suppresses auto numbering by mistake.
contract("NUM1 headings Python does not read as numbered are not marked", "xfail", async () => {
  const session = await boot();
  try {
    const falsePositives = session.numbered().filter((text) => text.startsWith("2）"));
    assert.deepEqual(falsePositives, [],
      "a heading Python reads as unnumbered must not get no-autonumber");
  } finally {
    session.close();
  }
});

// ── NUM2 (V10): the three forms Python DOES read as numbered must be marked. ─
contract("NUM2 every heading Python reads as numbered is marked", "xfail", async () => {
  const session = await boot();
  try {
    const numbered = session.numbered();
    for (const text of ["一、乙组", "1．2 丁组", "第1章 丙"]) {
      assert.ok(
        numbered.some((entry) => entry.startsWith(text)),
        "missing no-autonumber on " + JSON.stringify(text),
      );
    }
  } finally {
    session.close();
  }
});



