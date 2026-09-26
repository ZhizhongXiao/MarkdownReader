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

// ── Theme layer (Phase 6C) ───────────────────────────────────────────────────
// The reader carries every builtin theme and switches at runtime. These
// contracts are the executable form of the contract in docs/VIEWER_CONTRACT.md:
// the theme is a second, independent axis next to light/dark, and switching one
// never touches the other or rebuilds the document.
const THEME_ID_ATTR = "data-theme-id";
const THEME_STORAGE = "markdownreader-theme-id";
const BUILTIN_THEMES = ["modern", "office", "vscode"];

function themeMenu(session, themeId) {
  const option = session.doc.querySelector('#theme-menu [data-theme-id="' + themeId + '"]');
  assert.ok(option, "the theme menu must offer " + themeId);
  return option;
}

function isMenuOpen(session) {
  const menu = session.doc.getElementById("theme-menu");
  assert.ok(menu, "the page must carry a #theme-menu element");
  return !menu.hasAttribute("hidden");
}

function activeThemeId(session) {
  return session.doc.documentElement.getAttribute(THEME_ID_ATTR);
}

function switchTheme(session, themeId) {
  session.clickToolbar("btn-theme");
  assert.ok(isMenuOpen(session), "clicking the theme button must open the menu");
  session.click(themeMenu(session, themeId));
  assert.ok(!isMenuOpen(session), "picking a theme must close the menu");
}

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
const SCROLL_KEY = "markdownreader-scroll-" + pathnameOf("A");

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
contract("F1 manual fold survives a reload", "pass", async () => {
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

// ── F2 (V1): a manual collapse must survive a level round trip. ─────────────
contract("F2 manual collapse survives a level round trip", "pass", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "4" } });
  try {
    // The discriminator is one specific descendant, never a document total: a
    // level change legitimately changes how much the baseline hides, so a count
    // cannot separate "the override was kept" from "the baseline moved".
    //
    // At level 4 the only baseline-collapsed heading is the h5, which has no
    // children, so nothing is hidden to begin with. Collapsing the h4 hides its
    // h5 child: that is the override's own, unmasked effect.
    const parent = h(session, "乙一子项");
    const child = h(session, "乙一深项");
    assert.equal(session.isHidden(child), false, "precondition: level 4 leaves the h5 visible");

    session.clickHeadingToggle(parent);
    assert.equal(session.isHidden(child), true, "precondition: the manual collapse hid the h5");

    // 4 -> 3 makes the baseline catch up with the manual decision, which is
    // exactly the moment a naive "drop anything equal to the baseline" prune
    // would throw the user's decision away.
    session.clickToolbar(COLLAPSE);
    // 3 -> 4 moves the baseline away again, so only a kept override can still
    // hide the h5.
    session.clickToolbar(ADVANCE);

    assert.equal(
      session.isHidden(child),
      true,
      "a level round trip must not discard a manual collapse",
    );
  } finally {
    session.close();
  }
});

// ── F3 (V1): a manual expand must survive a level round trip. ───────────────
contract("F3 manual expand survives a level round trip", "pass", async () => {
  const session = await boot({ seed: { [LEGACY_FOLD_KEY]: "3" } });
  try {
    const parent = h(session, "乙一子项");
    const child = h(session, "乙一深项");
    assert.equal(session.isHidden(child), true, "precondition: level 3 hides the h5");

    session.clickHeadingToggle(parent);
    assert.equal(session.isHidden(child), false, "precondition: the manual expand revealed the h5");

    // 3 -> 4 makes the baseline catch up with the manual decision.
    session.clickToolbar(ADVANCE);
    // 4 -> 3 moves it away again; only a kept override keeps the h5 visible.
    session.clickToolbar(COLLAPSE);

    assert.equal(
      session.isHidden(child),
      false,
      "a level round trip must not discard a manual expand",
    );
  } finally {
    session.close();
  }
});

// ── F4: an override equal to the baseline is not worth storing. ─────────────
contract("F4 redundant overrides are pruned", "pass", async () => {
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
contract("F5 removed headings never break the stored state", "pass", async () => {
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
contract("M1 legacy level migrates into the v2 document state", "pass", async () => {
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
contract("M2 damaged legacy levels are restored, never guessed", "pass", async () => {
  const cases = [["-1", 0], ["7", 6], ["not-a-number", 6], ["3abc", 6]];
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
contract("D1 same title, different pathname: positions never leak", "pass", async () => {
  const a = await boot({ variant: "A" });
  const b = await boot({ variant: "B" });
  try {
    assert.equal(a.doc.title, b.doc.title, "precondition: both fixtures carry the same title");
    assert.notEqual(
      a.window.location.pathname,
      b.window.location.pathname,
      "precondition: their pathnames differ",
    );
  } finally {
    a.close();
    b.close();
  }

  // The reading position belongs to one document, identified by its PATH. The
  // old global title key is deliberately NOT honoured as a fallback: reading
  // position is short-lived state, and a title fallback would reintroduce the
  // very leak this contract is about.
  const seed = { ["markdownreader-scroll-" + pathnameOf("A")]: "500" };

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
contract("S2 scrolling is persisted without waiting for unload", "pass", async () => {
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
contract("S2b pagehide forces a save", "pass", async () => {
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

// ── S2c (V7): saving must tell the reader apart from the restore itself. ────
// Two halves on purpose. Half 1 overlaps S2, but without it this contract would
// be vacuous before V7 exists (there is no scroll listener at all yet, so
// "nothing was written during the restore" would trivially hold). Half 2 is the
// one that rejects the naive implementation: `scroll -> throttled save` would
// persist the mid-restore position, and a page closed mid-animation would
// overwrite a correct position with that wrong one.
contract("S2c the restore animation is never persisted as reading progress", "pass", async () => {
  const fresh = await boot();
  try {
    fresh.scrollTo(420);
    await fresh.sleep(400);
    assert.ok(
      JSON.stringify(fresh.storage()).includes("420"),
      "a user scroll must still be persisted while reading",
    );
  } finally {
    fresh.close();
  }

  const restoring = await boot({ seed: { [LEGACY_FOLD_KEY]: "3", [SCROLL_KEY]: "500" } });
  try {
    await restoring.frames(3);
    const settled = JSON.stringify(restoring.storage());

    // A mid-animation position, deliberately different from the saved 500.
    restoring.area.scrollTop = 180;
    restoring.area.dispatchEvent(new restoring.window.Event("scroll"));
    await restoring.sleep(500);
    assert.equal(
      JSON.stringify(restoring.storage()),
      settled,
      "progress produced by the programmatic restore must not be persisted",
    );

    // Once the restore window is over, ordinary reading progress is saved again.
    restoring.area.dispatchEvent(new restoring.window.Event("scrollend"));
    restoring.scrollTo(640);
    await restoring.sleep(400);
    assert.ok(
      JSON.stringify(restoring.storage()).includes("640"),
      "after the restore window closes, a user scroll must be persisted again",
    );
  } finally {
    restoring.close();
  }
});

// ── T1 (V3): a passive observer must never change user TOC folds. ───────────
contract("T1 the scroll spy never changes user-collapsed TOC branches", "pass", async () => {
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
// Two assertions on purpose, so a half-implementation cannot satisfy this by
// marking both rows: the hidden row must NOT be active, and its nearest visible
// ancestor must be.
contract("T2 the active heading is indicated without expanding its branch", "pass", async () => {
  const session = await boot();
  try {
    const branch = h(session, "1.1 甲组");
    const hiddenTarget = h(session, "一、乙组");
    session.clickTocToggle(branch.id);
    session.fireSpy(hiddenTarget.id);

    assert.equal(
      session.tocRow(hiddenTarget.id).classList.contains("active"),
      false,
      "a hidden TOC row must not carry the visible active marker",
    );
    assert.ok(
      session.tocRow(branch.id).classList.contains("active"),
      "the nearest visible ancestor must carry the active marker instead",
    );
    assert.deepEqual(session.tocCollapsedIds(), [branch.id],
      "and that branch must stay collapsed");
  } finally {
    session.close();
  }
});

// ── N1 (V4): explicit navigation may unfold whatever blocks the jump. ───────
contract("N1 TOC navigation unfolds a target hidden by the content fold", "pass", async () => {
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
contract("N2 navigation-induced unfolding is persisted as an override", "pass", async () => {
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
contract("P1 collapsing a section never clears the hidden class elsewhere", "pass", async () => {
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
contract("NUM1 headings Python does not read as numbered are not marked", "pass", async () => {
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
contract("NUM2 every heading Python reads as numbered is marked", "pass", async () => {
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

// ── E1 (7.4): a normal interaction session raises nothing. ─────────────────
// Stage 7.1 taught the harness to see an exception thrown inside a DOM listener,
// but the only assertions on it are the two at init time. A throw during an
// interaction would therefore be visible to the harness and still unnoticed by
// the suite. This record closes that hole: it drives the ordinary interactions
// and requires the error list to stay empty after every one of them.
//
// It is a regression lock, not a fix. The sequence below was measured against the
// real fixture and produces no errors and no jsdom notices on the current page.
contract("E1 a normal interaction session raises no uncaught exception", "pass", async () => {
  const session = await boot();
  try {
    const steps = [
      ["heading toggle", function () { session.clickHeadingToggle(h(session, "1.1 甲组")); }],
      ["toc link", function () { session.clickTocLink(h(session, "一、乙组").id); }],
      ["expand all", function () { session.clickToolbar(ADVANCE); }],
      ["collapse all", function () { session.clickToolbar(COLLAPSE); }],
      ["scroll write", function () { session.scrollTo(240); }],
      ["scroll event", function () {
        session.area.dispatchEvent(new session.window.Event("scroll"));
      }],
      ["scroll spy", function () { session.fireSpy(h(session, "1.1 甲组").id, true); }],
    ];

    assert.deepEqual(session.sentinels().errors, [], "precondition: init logged nothing");

    for (const entry of steps) {
      entry[1]();
      assert.deepEqual(session.sentinels().errors, [],
        "an uncaught page exception appeared at step " + entry[0] + ": "
        + JSON.stringify(session.sentinels().errors));
    }
  } finally {
    session.close();
  }
});
contract("L1 lightbox: the wheel zooms the opened image and the overlay still closes", "pass", async () => {
  const session = await boot();
  try {
    const body = session.doc.getElementById("markdown-body");
    const image = session.doc.createElement("img");
    image.src = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";
    image.alt = "示例图";
    body.appendChild(image);

    // The fixture has no image, so the contract adds one: the handler under test is
    // delegated on the body, which is exactly what a real image would trigger.
    image.dispatchEvent(new session.window.MouseEvent("click", { bubbles: true }));
    const overlay = session.doc.querySelector(".lightbox-overlay");
    assert.ok(overlay, "clicking an image must open the lightbox");
    const large = overlay.querySelector("img");
    assert.equal(large.src, image.src, "the lightbox shows the same image");
    assert.equal(large.style.transform, "", "it opens at the fitted size");

    const wheel = (deltaY) => {
      const event = new session.window.Event("wheel", { bubbles: true, cancelable: true });
      Object.defineProperty(event, "deltaY", { value: deltaY });
      overlay.dispatchEvent(event);
      return Number(String(large.style.transform).replace(/[^0-9.]/g, "")) || 1;
    };

    const enlarged = wheel(-120);
    assert.ok(enlarged > 1, "a wheel up must enlarge the image, got " + enlarged);

    let capped = enlarged;
    for (let index = 0; index < 40; index += 1) capped = wheel(-120);
    assert.ok(capped <= 6.001, "the zoom must stop at its ceiling, got " + capped);

    const shrunken = wheel(120);
    assert.ok(shrunken < capped, "a wheel down must shrink it again, got " + shrunken);

    overlay.dispatchEvent(new session.window.MouseEvent("click", { bubbles: true }));
    assert.equal(session.doc.querySelector(".lightbox-overlay"), null,
      "the overlay must still close while zoomed");
  } finally {
    session.close();
  }
});

// ── THEME1: the initial theme is the document's own default. ────────────────
// The office fixture (variant C) is used on purpose: "falls back to the document
// default" is only distinguishable from "hardcodes modern" on a document that is
// not modern.
contract("THEME1 the initial theme is the document default", "pass", async () => {
  for (const [variant, themeId] of [["A", "modern"], ["C", "office"]]) {
    const session = await boot({ variant });
    try {
      assert.equal(session.doc.documentElement.getAttribute(THEME_ID_ATTR), themeId,
        "document " + variant + " must start on " + themeId);
      assert.ok(session.doc.body.classList.contains("theme-" + themeId),
        "the body class must agree with data-theme-id");
    } finally {
      session.close();
    }
  }
});

// ── THEME2: switching moves both markers together. ──────────────────────────
contract("THEME2 switching updates data-theme-id and the body class together", "pass", async () => {
  const session = await boot();
  try {
    // A class that merely *looks* like a theme class must survive a switch: the
    // switcher owns the classes of the themes this document carries, not every name
    // that happens to start with "theme-". Without this the assertion below passes
    // on an implementation that wipes the whole prefix.
    session.doc.body.classList.add("theme-product-marker");

    switchTheme(session, "office");
    assert.equal(activeThemeId(session), "office");
    assert.ok(session.doc.body.classList.contains("theme-office"));
    assert.ok(!session.doc.body.classList.contains("theme-modern"),
      "the previous theme class must be removed, not kept alongside");
    assert.ok(session.doc.body.classList.contains("theme-product-marker"),
      "a non-theme class must survive: body class = " + session.doc.body.className);

    switchTheme(session, "vscode");
    assert.equal(activeThemeId(session), "vscode");
    assert.ok(session.doc.body.classList.contains("theme-vscode"));
    assert.ok(!session.doc.body.classList.contains("theme-office"));
    assert.ok(session.doc.body.classList.contains("theme-product-marker"),
      "and it must still survive the second switch");
  } finally {
    session.close();
  }
});

// ── THEME3: the choice survives a reload. ───────────────────────────────────
contract("THEME3 the selected theme persists across a reload", "pass", async () => {
  const first = await boot();
  let storage;
  try {
    switchTheme(first, "vscode");
    storage = first.storage();
    assert.equal(storage[THEME_STORAGE], "vscode",
      "the choice must be persisted under " + THEME_STORAGE);
  } finally {
    first.close();
  }

  const reloaded = await boot({ seed: storage });
  try {
    assert.equal(activeThemeId(reloaded), "vscode", "a reload must keep the choice");
    assert.ok(reloaded.doc.body.classList.contains("theme-vscode"));
  } finally {
    reloaded.close();
  }
});

// ── THEME4: a stale choice falls back to the document default. ──────────────
contract("THEME4 a stale stored theme falls back to the document default", "pass", async () => {
  const session = await boot({ variant: "C", seed: { [THEME_STORAGE]: "paper-from-2019" } });
  try {
    assert.equal(activeThemeId(session), "office",
      "an unknown id must fall back to the document's own default, not to modern");
    assert.ok(session.doc.body.classList.contains("theme-office"));
  } finally {
    session.close();
  }
});

// ── THEME5: switching is a CSS state change, not a re-render. ───────────────
contract("THEME5 switching a theme keeps the markdown DOM identity", "pass", async () => {
  const session = await boot();
  try {
    const body = session.body;
    const child = body.firstElementChild;
    assert.ok(child, "precondition: the fixture has content");

    switchTheme(session, "office");

    assert.strictEqual(session.doc.getElementById("markdown-body"), body,
      "the content container must be the same node");
    assert.strictEqual(body.firstElementChild, child,
      "the content nodes must be the same objects, not an equal copy");
    assert.equal(session.doc.querySelectorAll("#markdown-body").length, 1,
      "there must still be exactly one content container");
  } finally {
    session.close();
  }
});

// ── THEME6: switching a theme leaves light/dark alone. ──────────────────────
contract("THEME6 switching a theme does not change light/dark", "pass", async () => {
  const session = await boot();
  try {
    session.clickToolbar("btn-dark-mode");
    assert.equal(session.doc.documentElement.getAttribute("data-theme"), "dark",
      "precondition: dark mode is on");

    switchTheme(session, "office");

    assert.equal(session.doc.documentElement.getAttribute("data-theme"), "dark",
      "the colour scheme must be untouched by a theme switch");
    assert.equal(session.storage()["markdownreader-theme"], "dark",
      "and its stored value must be untouched too");
  } finally {
    session.close();
  }
});

// ── THEME7: light/dark leaves the theme alone. ──────────────────────────────
contract("THEME7 switching light/dark does not change the theme", "pass", async () => {
  const session = await boot();
  try {
    switchTheme(session, "vscode");
    session.clickToolbar("btn-dark-mode");
    session.clickToolbar("btn-dark-mode");

    assert.equal(activeThemeId(session), "vscode", "the theme must survive dark/light toggles");
    assert.ok(session.doc.body.classList.contains("theme-vscode"));
    assert.equal(session.doc.documentElement.getAttribute("data-theme"), null,
      "back to light means the attribute is absent, and that is not a theme");
  } finally {
    session.close();
  }
});

// ── THEME8: every builtin theme is offered, with a readable name. ───────────
contract("THEME8 all three builtin themes are selectable", "pass", async () => {
  const session = await boot();
  try {
    session.clickToolbar("btn-theme");
    const offered = Array.from(
      session.doc.querySelectorAll("#theme-menu [data-theme-id]"),
    ).map((option) => option.getAttribute("data-theme-id")).sort();

    assert.deepEqual(offered, BUILTIN_THEMES.slice().sort(),
      "the menu must offer exactly the selectable builtin themes");
    for (const themeId of BUILTIN_THEMES) {
      const label = themeMenu(session, themeId).textContent.trim();
      assert.ok(label.length > 0, "option " + themeId + " needs a readable label");
      assert.notEqual(label, themeId, "the label must be a human name, not the id");
    }
  } finally {
    session.close();
  }
});
