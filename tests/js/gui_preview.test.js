// Phase 12 GUI closeout - the theme model on the main page.
//
// The retired product behaviour was a builtin "template" dropdown that chose the document's
// default theme. The closeout replaces it with two independent states that this file locks
// apart:
//
//   preview  which theme the right-hand static stage shows; it belongs to this GUI session and
//            changes nothing that gets saved;
//   carry    which installed external themes the next document carries; it is the only theme
//            state that reaches config.json and the generated HTML.
//
// Builtin themes have a preview and no carry state; external themes have both, and the two are
// driven by different controls (row click vs. checkbox). A theme without preview metadata is
// still a working theme, so the illustrated stage is hidden and a text notice is shown instead of
// treating the theme as an error.
//
// Expectations are declared like every other suite here: "pass" must hold, "xfail" is a strict
// known-broken contract that fails the suite once it starts passing.

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { bootGui } from "./gui_harness.mjs";

const GUI_CSS = readFileSync(new URL("../../gui/assets/gui.css", import.meta.url), "utf8");

function cssDeclarations(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const rule = new RegExp(escaped + "\\s*\\{([^}]*)\\}").exec(GUI_CSS);
  assert.ok(rule, "GUI stylesheet must define " + selector);
  const declarations = {};
  rule[1].split(";").forEach(function (part) {
    const separator = part.indexOf(":");
    if (separator < 0) return;
    declarations[part.slice(0, separator).trim()] = part.slice(separator + 1).trim();
  });
  return declarations;
}

const PREVIEW = {
  background: "#f2eee5",
  surface: "#fffdf8",
  text: "#302b25",
  muted: "#81776b",
  accent: "#956439",
  border: "#d6c6b2",
};

// Two installed user themes: one with tokens, one without preview metadata at all.
const TWO_THEME_STATE = {
  default: "modern",
  installed: ["paper", "ink"],
  configured: [],
  selected: [],
  missing: [],
  invalid: [],
  installed_invalid: [],
  warnings: [],
  previews: {
    paper: {
      name: "Paper",
      description: "暖色纸张 · 正文长边饰",
      preview: PREVIEW,
      preview_status: "available",
      preview_reason: "",
    },
    ink: {
      name: "Ink",
      description: "只改排版的极简主题",
      preview: null,
      preview_status: "missing",
      preview_reason: "metadata.json 未提供 preview",
    },
  },
};

function contract(name, expectation, body) {
  test(name, async (t) => {
    let failure = null;
    try { await body(t); } catch (error) { failure = error; }
    const status = expectation === "xfail"
      ? (failure ? "xfail" : "xpass")
      : (failure ? "fail" : "pass");
    console.log("CONTRACT " + status + " " + name);
    if (status === "xfail") {
      t.diagnostic("xfail (expected): " + String(failure.message || failure).split("\n")[0]);
      return;
    }
    if (status === "xpass") throw new Error("XPASS: contract now holds - flip its marker to pass");
    if (status === "fail") throw failure;
  });
}

// ── Probes (DOM only, like every probe in the other suites) ─────────────────────

function previewButton(session, direction) {
  const id = direction === "previous" ? "btn-preview-prev" : "btn-preview-next";
  return session.list(id);
}

async function stepPreview(session, direction, count = 1) {
  const button = previewButton(session, direction);
  assert.ok(button, "the ordered preview control must exist: " + direction);
  for (let i = 0; i < count; i += 1) {
    button.click();
    await session.flush(2);
  }
}

function previewStage(session) {
  const stage = session.list("theme-preview");
  if (!stage) return null;
  return {
    id: stage.getAttribute("data-preview-theme"),
    classes: Array.prototype.slice.call(stage.classList),
    style: stage.getAttribute("style") || "",
  };
}

function fallbackVisible(session) {
  const node = session.list("preview-fallback");
  if (!node) return null;
  return !node.classList.contains("hidden");
}

function rowNode(session, id) {
  return session.doc.querySelector('.theme-row[data-theme-id="' + id + '"]');
}

function rowCheckbox(session, id) {
  const row = rowNode(session, id);
  return row ? row.querySelector("input[type=\"checkbox\"]") : null;
}

// ── The preview surface ─────────────────────────────────────────────────────────

contract("GP1 preview surface: the tab and the stage are the theme preview", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    assert.equal(session.text("tab-preview"), "主题预览", "the workspace tab is the theme preview");
    assert.ok(session.list("theme-preview"), "#theme-preview must exist (Phase 12 GUI closeout)");
    assert.equal(session.list("template-preview"), null,
      "the retired #template-preview stage must be gone");
  } finally { session.close(); }
});

contract("GP2 ordered preview controls: accessible left and right triangles", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    const previous = previewButton(session, "previous");
    const next = previewButton(session, "next");
    assert.ok(previous && next, "both directions must be available");
    assert.equal(previous.textContent.trim(), "◀");
    assert.equal(next.textContent.trim(), "▶");
    assert.equal(previous.getAttribute("aria-label"), "上一个主题预览");
    assert.equal(next.getAttribute("aria-label"), "下一个主题预览");
    assert.equal(session.doc.querySelectorAll(".preview-nav-controls [data-preview-theme]").length, 0,
      "navigation controls move through the sequence instead of selecting random per-theme buttons");
  } finally { session.close(); }
});

contract("GP3 preview order: next and previous step through the fixed cycle and wrap", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    const expected = ["office", "vscode", "paper", "ink", "modern"];
    for (const id of expected) {
      await stepPreview(session, "next");
      assert.equal(previewStage(session).id, id);
    }
    assert.equal(session.text("preview-theme-name"), "Modern", "the cycle wraps to its first theme");

    await stepPreview(session, "previous");
    assert.equal(previewStage(session).id, "ink", "previous moves one step back across the wrap");
    assert.equal(session.savePayloads().length, 0, "previewing is not a saved state");
  } finally { session.close(); }
});

contract("GP4 preview default: a session starts at Modern whatever the payload says", "pass", async () => {
  const state = JSON.parse(JSON.stringify(TWO_THEME_STATE));
  state.default = "office";
  const session = await bootGui({ themeState: state });
  try {
    const stage = previewStage(session);
    assert.ok(stage, "#theme-preview must exist (Phase 12 GUI closeout)");
    assert.equal(stage.id, "modern", "the preview starts at the bootstrap theme");
    assert.equal(session.savePayloads().length, 0, "booting must not save anything");
  } finally { session.close(); }
});

contract("GP5 external previews: exactly the installed, usable themes", "pass", async () => {
  const state = JSON.parse(JSON.stringify(TWO_THEME_STATE));
  state.installed = ["paper", "ink", "broken"];
  state.invalid = ["broken"];
  state.previews.broken = {
    name: "Broken", description: "", preview: null,
    preview_status: "missing", preview_reason: "",
  };
  const session = await bootGui({ themeState: state });
  try {
    assert.ok(rowNode(session, "broken"), "an unusable installation remains visible in the list");
    await stepPreview(session, "next", 3);
    assert.equal(previewStage(session).id, "paper");
    await stepPreview(session, "next");
    assert.equal(previewStage(session).id, "ink");
    await stepPreview(session, "next");
    assert.equal(previewStage(session).id, "modern", "unusable themes are skipped in the cycle");
  } finally { session.close(); }
});

contract("GP6 external preview: the nav never touches the carry checkbox", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    await stepPreview(session, "next", 3);
    const box = rowCheckbox(session, "paper");
    assert.ok(box, "the row keeps its carry checkbox");
    let clicks = 0;
    let changes = 0;
    box.addEventListener("click", function () { clicks += 1; });
    box.addEventListener("change", function () { changes += 1; });
    const before = box.checked;

    const stage = previewStage(session);
    assert.ok(stage, "#theme-preview must exist (Phase 12 GUI closeout)");
    assert.equal(stage.id, "paper");
    assert.equal(clicks, 0, "previewing must not click the carry checkbox");
    assert.equal(changes, 0, "previewing must not change the carry selection");
    assert.equal(box.checked, before, "the checkbox state is untouched");
    assert.equal(session.savePayloads().length, 0, "previewing writes nothing");
  } finally { session.close(); }
});

contract("GP7 theme rows: checkbox first, then name and description", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    const row = rowNode(session, "paper");
    assert.ok(row, ".theme-row[data-theme-id] must exist (Phase 12 GUI closeout)");
    const parts = Array.prototype.slice.call(
      row.querySelectorAll("input.theme-row-check, .theme-row-name, .theme-row-desc"));
    assert.deepEqual(parts.map(function (node) { return node.className.split(" ")[0]; }),
      ["theme-row-check", "theme-row-name", "theme-row-desc"],
      "the carry checkbox sits left of the name, and the description follows it");
    assert.equal(row.querySelector(".theme-row-name").textContent.trim(), "Paper");
    assert.equal(row.querySelector(".theme-row-desc").textContent.trim(), "暖色纸张 · 正文长边饰");
  } finally { session.close(); }
});

// ── One row, two controls ───────────────────────────────────────────────────────

contract("GP8 row click previews: the row body is not the carry control", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    const row = rowNode(session, "paper");
    assert.ok(row, ".theme-row[data-theme-id] must exist (Phase 12 GUI closeout)");
    const box = row.querySelector("input.theme-row-check");
    assert.ok(box, "the carry checkbox is marked with .theme-row-check");
    const name = row.querySelector(".theme-row-name");
    assert.ok(name, ".theme-row-name must exist (Phase 12 GUI closeout)");
    let changes = 0;
    box.addEventListener("change", function () { changes += 1; });
    const before = box.checked;

    name.click();
    await session.flush(2);

    const stage = previewStage(session);
    assert.ok(stage, "#theme-preview must exist (Phase 12 GUI closeout)");
    assert.equal(stage.id, "paper");
    assert.equal(changes, 0, "clicking the row body must not toggle carry");
    assert.equal(box.checked, before);
    assert.equal(session.savePayloads().length, 0);
  } finally { session.close(); }
});

contract("GP9 checkbox carries: it never moves the preview", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    const stage = previewStage(session);
    assert.ok(stage, "#theme-preview must exist (Phase 12 GUI closeout)");
    const box = rowCheckbox(session, "paper");
    assert.ok(box, "the row keeps its carry checkbox");

    box.checked = true;
    box.dispatchEvent(new session.window.Event("change", { bubbles: true }));
    await session.flush(3);
    await session.resolve("set_configs", null);
    await session.flush(3);

    const payloads = session.savePayloads();
    assert.equal(payloads.length, 1, "checking a theme writes exactly one payload");
    assert.deepEqual(Object.keys(payloads[0]), ["external_themes"]);
    assert.deepEqual(payloads[0].external_themes, ["paper"]);
    assert.equal(previewStage(session).id, stage.id, "carrying does not move the preview");
  } finally { session.close(); }
});

contract("GP10 previewing: the mark follows the preview, not the carry set", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    await stepPreview(session, "next", 3);

    const paperRow = rowNode(session, "paper");
    const inkRow = rowNode(session, "ink");
    assert.ok(paperRow && inkRow, ".theme-row[data-theme-id] must exist (Phase 12 GUI closeout)");
    assert.equal(paperRow.classList.contains("previewing"), true, "the previewed row is marked");
    assert.equal(inkRow.classList.contains("previewing"), false);

    const inkBox = inkRow.querySelector("input[type=\"checkbox\"]");
    inkBox.checked = true;
    inkBox.dispatchEvent(new session.window.Event("change", { bubbles: true }));
    await session.flush(3);
    await session.resolve("set_configs", null);
    await session.flush(3);

    assert.equal(inkRow.classList.contains("previewing"), false,
      "carrying a theme must not mark it as previewed");
    assert.equal(paperRow.classList.contains("previewing"), true,
      "the previewed row keeps its mark while carry changes");
  } finally { session.close(); }
});

contract("GP11 preview tokens: the stage shows the theme's own colours", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    await stepPreview(session, "next", 3);

    const stage = previewStage(session);
    assert.ok(stage, "#theme-preview must exist (Phase 12 GUI closeout)");
    assert.equal(stage.classes.indexOf("hidden"), -1,
      "a theme with preview metadata keeps the illustrative stage visible");
    assert.ok(stage.style.indexOf(PREVIEW.accent) !== -1,
      "the preview uses the theme accent token: " + stage.style);
    assert.ok(stage.style.indexOf(PREVIEW.background) !== -1, stage.style);
  } finally { session.close(); }
});

// ── No preview metadata ─────────────────────────────────────────────────────────

contract("GP12 no preview: a missing preview degrades to a notice", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    await stepPreview(session, "next", 4);

    const stage = previewStage(session);
    assert.ok(stage, "#theme-preview must remain available for the preview state");
    assert.notEqual(stage.classes.indexOf("hidden"), -1,
      "the entire illustrative stage is hidden when preview metadata is missing");
    assert.equal(fallbackVisible(session), true, "#preview-fallback must be shown");
    const previewLayout = cssDeclarations(".theme-preview");
    const fallbackLayout = cssDeclarations(".preview-fallback");
    ["flex", "min-width", "min-height", "width"].forEach(function (property) {
      assert.equal(fallbackLayout[property], previewLayout[property],
        "the text notice must use the same " + property + " sizing as the preview stage");
    });
    assert.equal(fallbackLayout["align-items"], "center");
    assert.equal(fallbackLayout["justify-content"], "center");
    assert.equal(fallbackLayout["text-align"], "center");
    assert.ok(session.text("preview-fallback").indexOf("未提供静态预览") !== -1,
      session.text("preview-fallback"));
    assert.equal(rowCheckbox(session, "ink").disabled, false,
      "a theme without preview metadata is still carryable");
    assert.equal(session.logErrorCount(), 0, "a missing preview is not an error");
  } finally { session.close(); }
});

contract("GP13 invalid preview: the same notice as a missing one", "pass", async () => {
  const state = JSON.parse(JSON.stringify(TWO_THEME_STATE));
  state.previews.ink.preview_status = "invalid";
  state.previews.ink.preview_reason = "preview.accent 不是 #rrggbb";
  const session = await bootGui({ themeState: state });
  try {
    await stepPreview(session, "next", 4);

    const stage = previewStage(session);
    assert.ok(stage, "#theme-preview must remain available for the preview state");
    assert.notEqual(stage.classes.indexOf("hidden"), -1,
      "the entire illustrative stage is hidden when preview metadata is invalid");
    assert.equal(fallbackVisible(session), true, "a broken preview degrades to the notice");
    assert.equal(rowCheckbox(session, "ink").disabled, false,
      "a broken preview never blocks carrying the theme");
    assert.equal(session.logErrorCount(), 0, "a broken preview is a GUI inconvenience");
  } finally { session.close(); }
});

contract("GP14 preview session: nothing is saved, no reader preference is written", "pass", async () => {
  const session = await bootGui({ themeState: TWO_THEME_STATE });
  try {
    await stepPreview(session, "previous");
    await stepPreview(session, "next", 2);
    assert.equal(previewStage(session).id, "office");

    assert.equal(session.savePayloads().length, 0, "previewing must not write configuration");
    assert.equal(session.window.localStorage.getItem("markdownreader-theme-id"), null,
      "the GUI must not write the reader's own preference");
  } finally { session.close(); }
});
