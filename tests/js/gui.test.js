// Stage 6.6a - GUI behaviour contracts (G0 liveness, GU1-GU7).
//
// Every contract drives the real gui.js through its public functions and
// observes the DOM and the recorded bridge calls. Expectations are declared the
// same way as the viewer layer: "pass" must hold today, "xfail" is a strict
// known-broken contract that fails the suite if it starts passing.

import test from "node:test";
import assert from "node:assert/strict";

import { bootGui } from "./gui_harness.mjs";

const PREPARE_SINGLE = process.env.MR_PREPARE_SINGLE_REQUEST;
const CONVERT_SINGLE = process.env.MR_CONVERT_SINGLE_REQUEST;

const PLAN_ONE = {
  inputs: ["C:\\docs\\a.md"],
  items: [{
    source_path: "C:\\docs\\a.md", input_path: "C:\\docs\\a.md",
    output_path: "output/a.html", output_relative: "a.html",
    origin: "selected", status: "pending", warnings: [],
  }],
  warnings: [], errors: [], output_dir: "output",
  counts: { selected: 1, directory: 0, dependency: 0, total: 1 },
};

const PLAN_TWO = {
  items: [PLAN_ONE.items[0], Object.assign({}, PLAN_ONE.items[0], {
    source_path: "C:\\docs\\b.md", input_path: "C:\\docs\\b.md",
    output_path: "output/b.html", output_relative: "b.html",
  })],
  warnings: [], errors: [], output_dir: "output",
  counts: { selected: 2, directory: 0, dependency: 0, total: 2 },
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

contract("GU0 liveness: the real GUI initialised against the stub", "pass", async () => {
  const session = await bootGui();
  try {
    const sentinels = session.sentinels();
    assert.equal(sentinels.readyState, "complete");
    assert.deepEqual(sentinels.errors, []);
    assert.equal(sentinels.dropOverlay, true);
    assert.equal(sentinels.conversionList, true);
    assert.equal(sentinels.logArea, true);
    assert.equal(sentinels.statusBadge, true);
    assert.ok(sentinels.templatesAsked !== 0, "init must ask for the templates");
    assert.ok(sentinels.configAsked !== 0, "init must ask for the config");
    assert.ok(sentinels.logLines !== 0, "init must have written a log line");
    assert.equal(session.conversionRows(), 0);
  } finally { session.close(); }
});

contract("GU1 bridge shape: both conversion calls send one structured request", "pass", async () => {
  const session = await bootGui();
  try {
    const first = PLAN_ONE.items[0].source_path;

    session.window.addInputs([first]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    session.window.runConvert();
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(3);
    await session.resolve("set_configs", null);
    await session.flush(3);

    const prepareCall = session.callsOf("prepare_conversion")[0];
    const convertCall = session.callsOf("convert")[0];
    assert.ok(prepareCall, "preflight must have called prepare_conversion");
    assert.ok(convertCall, "runConvert must have called convert");

    const prepareRequest = prepareCall.args[0];
    assert.equal(typeof prepareRequest, "object", "prepare_conversion takes an object request");
    assert.equal(Array.isArray(prepareRequest), false, "the request must not be an array");
    assert.deepEqual(Object.keys(prepareRequest).sort(),
      ["inputs", "output_dir", "preserve_structure"]);
    assert.deepEqual(Array.from(prepareRequest.inputs), [first]);
    assert.equal(prepareRequest.output_dir, "output");
    assert.equal(prepareRequest.preserve_structure, false);

    const convertRequest = convertCall.args[0];
    assert.equal(typeof convertRequest, "object", "convert takes an object request");
    assert.equal(Array.isArray(convertRequest), false, "the request must not be an array");
    assert.deepEqual(Object.keys(convertRequest).sort(),
      ["auto_open", "build_index", "inputs", "output_dir", "overwrite",
       "preserve_structure", "template"]);
    assert.deepEqual(Array.from(convertRequest.inputs), [first]);
    assert.equal(convertRequest.output_dir, "output");
    assert.equal(convertRequest.template, "modern");
    assert.equal(convertRequest.overwrite, true);
    assert.equal(convertRequest.build_index, true);
    assert.equal(convertRequest.auto_open, true);
    assert.equal(convertRequest.preserve_structure, false);

    assert.equal(PREPARE_SINGLE, "1", "gui/api.py::prepare_conversion must take self + one request");
    assert.equal(CONVERT_SINGLE, "1", "gui/api.py::convert must take self + one request");
  } finally { session.close(); }
});

contract("GU2 clear-inputs: a plan that resolves late must not come back", "pass", async () => {
  const session = await bootGui();
  try {
    const idleStatus = session.status();
    const first = PLAN_ONE.items[0].source_path;
    const second = PLAN_TWO.items[1].source_path;

    // A completed run first, so the open-HTML entry really carries a file.
    session.window.addInputs([first]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    session.window.runConvert();
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(3);
    await session.resolve("set_configs", null);
    await session.flush(3);
    await session.resolve("convert", {
      success: true, files: ["output/a.html"], entry_file: "output/a.html",
      errors: [], warnings: [], output_dir: "output",
      documents: [{ source_path: first, status: "success", warnings: [] }],
    });
    await session.flush(5);
    assert.equal(session.list("btn-open-file").disabled, false,
      "precondition: a completed run enables the open-HTML entry");

    // Now a pending preflight, a clear, and only then the stale response.
    session.window.addInputs([second]);
    await session.flush(3);
    session.window.clearInputs();
    await session.flush(1);
    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(5);

    const opensBefore = session.callsOf("open_file").length;
    session.window.openFile();
    await session.flush(3);

    assert.equal(session.conversionRows(), 0, "a stale plan must not repopulate the list");
    assert.deepEqual(session.status(), idleStatus, "clearing inputs must return the idle status");
    assert.equal(session.text("stat-total"), "0", "clearing inputs must reset the totals");
    assert.equal(session.list("btn-open-file").disabled, true,
      "clearing inputs must forget the previously produced file");
    assert.equal(session.callsOf("open_file").length, opensBefore,
      "the open-HTML entry must not open a forgotten file");
  } finally { session.close(); }
});

contract("GU3 terminal state: an untouched file is not a failure", "pass", async () => {
  const session = await bootGui();
  try {
    const first = PLAN_ONE.items[0].source_path;
    const second = PLAN_TWO.items[1].source_path;

    session.window.addInputs([first, second]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_TWO);
    session.window.runConvert();
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_TWO);
    await session.flush(3);
    await session.resolve("set_configs", null);
    await session.flush(3);
    await session.resolve("convert", {
      success: false, files: [], errors: ["boom"], output_dir: "output",
      documents: [{ source_path: first, status: "error", warnings: [] }],
    });
    await session.flush(5);

    const rows = session.list("conversion-list").children;
    assert.equal(rows.length, 2, "both documents stay listed after the run");
    assert.ok(rows[0].className.indexOf("status-error") !== -1,
      "a failure the backend reported keeps its error state");
    assert.ok(rows[1].className.indexOf("status-skipped") !== -1,
      "a file the run never reached is a terminal skipped state, not a failure");
    assert.equal(rows[1].querySelector(".conversion-status").title, "未转换",
      "and it says so, instead of implying the file itself failed");
    assert.equal(session.text("stat-error"), "1", "only the reported failure counts as an error");
    assert.equal(session.text("stat-pending"), "0", "a finished run leaves nothing pending");
  } finally { session.close(); }
});

contract("GU4 identity: the same document added twice is still one input", "pass", async () => {
  const session = await bootGui();
  try {
    const raw = "C:\\Docs\\x\\..\\a.md";
    const canonical = PLAN_ONE.inputs[0];

    session.window.addInputs([raw]);
    await session.flush(3);
    // The converter is the canonical authority for input spelling: it runs
    // abspath plus normpath and reports the result in plan.inputs. The GUI must
    // not grow its own Windows path parser.
    await session.resolve("prepare_conversion", {
      inputs: [canonical],
      items: [Object.assign({}, PLAN_ONE.items[0], { source_path: canonical })],
      warnings: [], errors: [], output_dir: "output",
      counts: { selected: 1, directory: 0, dependency: 0, total: 1 },
    });
    await session.flush(3);
    const single = session.text("input-summary");

    session.window.addInputs([canonical]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(3);

    assert.equal(session.text("input-summary"), single,
      "the canonical spelling of an added document must not become a second input");
  } finally { session.close(); }
});

contract("GU5 run snapshot: convert receives the confirmed plan, not live inputs", "pass", async () => {
  const session = await bootGui();
  try {
    const first = PLAN_ONE.items[0].source_path;
    const second = PLAN_TWO.items[1].source_path;

    session.window.addInputs([first]);
    await session.flush(3);
    const singleSummary = session.text("input-summary");
    await session.resolve("prepare_conversion", PLAN_ONE);
    session.window.runConvert();
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(3);

    // While the run is in flight the GUI state must not drift ...
    session.window.addInputs([second]);
    await session.flush(3);
    assert.equal(session.text("input-summary"), singleSummary,
      "the GUI state must not drift while a run is in flight");

    // ... and the bridge request must use the snapshot frozen at entry.
    await session.resolve("set_configs", null);
    await session.flush(3);

    const call = session.callsOf("convert")[0];
    assert.ok(call, "convert must have been called");
    assert.deepEqual(Array.from(call.args[0].inputs), [first],
      "the conversion request must use the plan snapshot that was confirmed");
  } finally { session.close(); }
});

contract("GU6 log badge: history survives and the badge states its own scope", "pass", async () => {
  const session = await bootGui();
  try {
    const first = PLAN_ONE.items[0].source_path;
    session.window.log("WARNING", "an earlier warning");

    session.window.addInputs([first]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    session.window.runConvert();
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(3);
    await session.resolve("set_configs", null);
    await session.flush(3);
    await session.resolve("convert", {
      success: false, files: [], errors: ["boom"], output_dir: "output", documents: [],
    });
    await session.flush(5);

    const area = session.list("log-area");
    const issueLines = session.logIssues();
    const badge = Number(session.text("log-issue-count"));
    const label = session.list("tab-log").getAttribute("aria-label") || "";

    assert.ok(issueLines !== 0, "the run must have logged an issue");
    assert.ok(area.children.length !== 1, "the earlier warning must still be in the log");
    assert.equal(badge, 1, "the badge counts this round, not the retained history");
    // Policy B keeps the history, so the badge is allowed to be a per-round
    // count - but only if its label says so. Otherwise it must match the log.
    const scoped = /本轮|新问题|未读/.test(label);
    if (!scoped) {
      assert.equal(badge, issueLines,
        "an unscoped problem count must equal the problems in the log");
    }

    for (let i = 0; i < 1200; i += 1) session.window.log("INFO", "filler " + i);
    await session.flush(3);
    assert.ok(area.children.length < 1200,
      "retained history needs a capacity cap, otherwise the log DOM grows forever");
  } finally { session.close(); }
});

contract("GU7 stats: the error stat counts documents only", "pass", async () => {
  const session = await bootGui();
  try {
    session.window.addInputs(["C:\\docs\\a.md"]);
    await session.flush(3);
    await session.resolve("prepare_conversion", Object.assign({}, PLAN_ONE, {
      errors: ["plan problem one", "plan problem two"],
    }));
    await session.flush(3);

    const observed = session.text("stat-error");
    assert.equal(observed, "0",
      "plan messages are not failed documents, but the stat read " + observed);
  } finally { session.close(); }
});

contract("GU8 dialog lock: one dialog at a time disables the other controls", "pass", async () => {
  const session = await bootGui();
  try {
    const filesButton = session.doc.getElementById("btn-select-files");
    const dirButton = session.doc.getElementById("btn-select-dir");
    const outputButton = session.doc.getElementById("btn-select-output");
    assert.ok(filesButton && dirButton && outputButton,
      "the three dialog controls must exist");

    session.window.selectFiles();
    await session.flush(2);
    assert.equal(session.callsOf("select_input_files").length, 1,
      "the first click must open exactly one dialog");
    assert.equal(filesButton.disabled, true, "the control in use is disabled");
    assert.equal(dirButton.disabled, true, "another control must be disabled too");
    assert.equal(outputButton.disabled, true, "another control must be disabled too");

    // The other controls must not reach the bridge while the first dialog is open.
    session.window.selectDir();
    session.window.selectOutput();
    await session.flush(2);
    assert.equal(session.callsOf("select_input_directory").length, 0,
      "a second dialog must not be opened");
    assert.equal(session.callsOf("select_output_directory").length, 0,
      "a second dialog must not be opened");

    await session.resolve("select_input_files", []);
    assert.equal(filesButton.disabled, false, "the controls come back");
    assert.equal(dirButton.disabled, false, "the controls come back");
    assert.equal(outputButton.disabled, false, "the controls come back");
  } finally { session.close(); }
});

// ── Phase 9A: the external theme selection surface ─────────────────────────────
//
// The state comes from the bridge, so every contract below hands the page a state and
// then reads the DOM. Two facts stay separate on purpose (AGENTS section 17): what the
// configuration remembers (`configured`) and what a document can use right now
// (`selected`, with `missing` / `invalid` saying why the rest cannot be restored). A
// theme that is merely gone must never be dropped from that memory silently.

const CONVERT_OK = {
  success: true,
  files: ["output/a.html"],
  errors: [],
  warnings: [],
  documents: [{
    source_path: "C:\\docs\\a.md", input_path: "C:\\docs\\a.md",
    output_path: "output/a.html", output_relative: "a.html",
    origin: "selected", status: "success", warnings: [],
  }],
  output_dir: "output",
  entry_file: "output/a.html",
};

// `broken` is installed *and* remembered, which is what makes it invalid; `ghost` is
// remembered but not installed, which is what makes it missing; `academic` and `zeta`
// are installed and selectable.
const THEME_STATE_A = {
  default: "modern",
  installed: ["academic", "broken", "paper", "zeta"],
  configured: ["paper", "ghost", "broken"],
  selected: ["paper"],
  missing: ["ghost"],
  invalid: ["broken"],
  warnings: ["外置主题当前未安装：ghost", "外置主题当前不可用：broken"],
};

// Two selectable themes are already remembered, so an uncheck has something to remove
// from the middle of the order rather than from its end.
const THEME_STATE_B = {
  default: "modern",
  installed: ["academic", "broken", "paper", "zeta"],
  configured: ["paper", "academic", "ghost", "broken"],
  selected: ["paper", "academic"],
  missing: ["ghost"],
  invalid: ["broken"],
  warnings: [],
};

const THEME_STATE_EMPTY = {
  default: "modern",
  installed: [], configured: [], selected: [], missing: [], invalid: [], warnings: [],
};

// The same facts with warning text that contradicts them: a surface that classified by
// reading the warnings would render this state wrong.
const THEME_STATE_MISLEADING = Object.assign({}, THEME_STATE_A, {
  warnings: [
    "外置主题当前未安装：academic",
    "外置主题当前不可用：zeta",
    "已忽略未安装的外置主题：paper",
  ],
});

function themeIdList(rows) {
  return (rows || []).map(function (row) { return row.id; }).sort();
}

contract("GT1 theme rows: selected, available, missing and invalid render apart", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    const rows = session.themeRows();
    assert.ok(rows, "the main page must carry the external theme surface");
    assert.deepEqual(themeIdList(rows), ["academic", "broken", "ghost", "paper", "zeta"]);

    assert.deepEqual(session.themeRow("paper"),
      { id: "paper", state: "selected", checked: true, disabled: false,
        removable: false, removeDisabled: null });
    assert.deepEqual(session.themeRow("academic"),
      { id: "academic", state: "available", checked: false, disabled: false,
        removable: false, removeDisabled: null });
    assert.deepEqual(session.themeRow("zeta"),
      { id: "zeta", state: "available", checked: false, disabled: false,
        removable: false, removeDisabled: null });
    assert.equal(session.themeRow("ghost").state, "missing");
    assert.equal(session.themeRow("ghost").checked, false);
    assert.equal(session.themeRow("ghost").disabled, true);
    assert.equal(session.themeRow("broken").state, "invalid");
    assert.equal(session.themeRow("broken").checked, false);
    assert.equal(session.themeRow("broken").disabled, true);

    assert.deepEqual(session.themeSummary(), { selected: "1", missing: "1", invalid: "1" });
    assert.equal(session.themeEmptyVisible(), false);
    assert.equal(session.callsOf("set_configs").length, 0,
      "rendering a state must never write the configuration");
  } finally { session.close(); }
});

contract("GT2 theme rows: only a remembered unusable theme can be removed", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    const ghost = session.themeRow("ghost");
    const broken = session.themeRow("broken");
    assert.notEqual(ghost.state, broken.state,
      "a theme that is gone and a theme that is broken are different states");
    assert.equal(ghost.removable, true, "a missing id can be dropped from the memory");
    assert.equal(ghost.removeDisabled, false);
    assert.equal(broken.removable, true, "an invalid id can be dropped from the memory");
    assert.equal(broken.removeDisabled, false);
    assert.equal(session.themeRow("academic").removable, false,
      "an installed theme is carried by checking it, not by removing it");
    assert.equal(session.themeRow("paper").removable, false);
  } finally { session.close(); }
});

contract("GT3 theme rows: the classification is read from fields, never from warning text", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_MISLEADING });
  try {
    assert.equal(session.themeRow("academic").state, "available",
      "a warning that names it must not demote an installed theme");
    assert.equal(session.themeRow("zeta").state, "available",
      "a warning that names it must not demote an installed theme");
    assert.equal(session.themeRow("paper").state, "selected",
      "a warning that names it must not demote the remembered selection");
    assert.equal(session.themeRow("ghost").state, "missing", "the missing field owns this state");
    assert.equal(session.themeRow("broken").state, "invalid", "the invalid field owns this state");
    assert.equal(session.themeRow("ghost").disabled, true);
    assert.equal(session.themeRow("broken").disabled, true);
  } finally { session.close(); }
});

contract("GT4 theme selection: checking a theme appends it and keeps the remembered order", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    session.window.toggleExternalTheme("academic");
    await session.flush(3);

    assert.equal(session.callsOf("set_configs").length, 1, "one change is one save");
    assert.deepEqual(Array.from(session.savePayloads()[0].external_themes),
      ["paper", "ghost", "broken", "academic"],
      "the remembered order is kept and the new id goes to the end");
    assert.equal(session.themeRow("academic").checked, true);

    await session.resolve("set_configs", null);
    session.window.toggleExternalTheme("zeta");
    await session.flush(3);
    assert.deepEqual(Array.from(session.savePayloads()[1].external_themes),
      ["paper", "ghost", "broken", "academic", "zeta"],
      "a second check appends after the first one");
    await session.resolve("set_configs", null);
  } finally { session.close(); }
});

contract("GT5 theme selection: unchecking a remembered theme removes only that id", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_B });
  try {
    session.window.toggleExternalTheme("paper");
    await session.flush(3);

    assert.equal(session.themeRow("paper").checked, false);
    assert.equal(session.themeRow("academic").checked, true,
      "the other remembered theme keeps its state");
    assert.deepEqual(Array.from(session.savePayloads()[0].external_themes),
      ["academic", "ghost", "broken"],
      "only the unchecked id leaves, and the rest keep the remembered order");
    await session.resolve("set_configs", null);
  } finally { session.close(); }
});

contract("GT6 theme selection: dropping an unusable remembered id removes only that id", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_B });
  try {
    session.window.removeConfiguredTheme("ghost");
    await session.flush(3);
    assert.deepEqual(Array.from(session.savePayloads()[0].external_themes),
      ["paper", "academic", "broken"], "a missing id is dropped on its own");
    await session.resolve("set_configs", null);

    session.window.removeConfiguredTheme("broken");
    await session.flush(3);
    assert.deepEqual(Array.from(session.savePayloads()[1].external_themes),
      ["paper", "academic"], "an invalid id is dropped on its own");
    await session.resolve("set_configs", null);
  } finally { session.close(); }
});

contract("GT7 theme selection: every save carries the whole working selection", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_B });
  try {
    assert.equal(session.callsOf("set_configs").length, 0, "booting is a read");

    session.window.toggleExternalTheme("zeta");
    await session.flush(3);

    const payload = session.savePayloads()[0];
    assert.deepEqual(Object.keys(payload), ["external_themes"],
      "the theme surface writes the theme list and nothing else");
    assert.deepEqual(Array.from(payload.external_themes),
      ["paper", "academic", "ghost", "broken", "zeta"],
      "the payload is the working selection, not the usable subset");
    assert.ok(payload.external_themes.indexOf("ghost") !== -1,
      "a merely missing id stays in the memory");
    assert.ok(payload.external_themes.indexOf("broken") !== -1,
      "an unusable id stays in the memory until the user drops it");
    await session.resolve("set_configs", null);
  } finally { session.close(); }
});

contract("GT8 theme selection: a refused save hands the page back to the bridge state", "pass", async () => {
  const session = await bootGui({ autoThemeState: false });
  try {
    await session.resolve("get_theme_state", THEME_STATE_A);
    assert.equal(session.themeRow("paper").checked, true, "the first state is rendered");

    session.window.toggleExternalTheme("academic");
    await session.flush(3);
    await session.reject("set_configs", new Error("boom"));

    assert.equal(session.callsOf("get_theme_state").length, 2,
      "a refused save must ask the bridge what is true instead of trusting the page");
    assert.ok(session.logErrorCount() >= 1, "the refusal must be visible in the log");

    // The page must rebuild from what the bridge reports, not from what it assumed:
    // the state that comes back remembers a different id than the failed change did.
    const afterFailure = Object.assign({}, THEME_STATE_EMPTY, {
      installed: ["zeta"], configured: ["zeta"], selected: ["zeta"],
    });
    await session.resolve("get_theme_state", afterFailure);
    assert.deepEqual(themeIdList(session.themeRows()), ["zeta"]);
    assert.equal(session.themeRow("zeta").checked, true);
    assert.equal(session.callsOf("set_configs").length, 1,
      "the refetch itself must not write anything");

    session.window.toggleExternalTheme("zeta");
    await session.flush(3);
    assert.deepEqual(Array.from(session.savePayloads()[1].external_themes), [],
      "the rebuilt selection is what gets saved, not the change that failed");
    await session.resolve("set_configs", null);
  } finally { session.close(); }
});

contract("GT9 theme selection: at most one write is in flight", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    session.window.toggleExternalTheme("academic");
    await session.flush(3);
    session.window.toggleExternalTheme("zeta");
    await session.flush(3);

    assert.equal(session.callsOf("set_configs").length, 1,
      "the second change must not open a second write");
    assert.equal(session.pendingOf("set_configs").length, 1);
    assert.deepEqual(Array.from(session.savePayloads()[0].external_themes),
      ["paper", "ghost", "broken", "academic"],
      "the write in flight is the state that existed when it started");

    await session.resolve("set_configs", null);
    await session.resolve("set_configs", null);
  } finally { session.close(); }
});

contract("GT10 theme selection: writes are serialised so an older payload never lands last", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    session.window.toggleExternalTheme("academic");
    await session.flush(3);
    session.window.toggleExternalTheme("zeta");
    await session.flush(3);
    assert.equal(session.callsOf("set_configs").length, 1,
      "the change that arrived while a write was in flight is held back");

    await session.resolve("set_configs", null);
    assert.equal(session.callsOf("set_configs").length, 2,
      "the held change is committed once the first write settled");

    const committed = session.savePayloads().map(function (payload) {
      return Array.from(payload.external_themes);
    });
    assert.deepEqual(committed, [
      ["paper", "ghost", "broken", "academic"],
      ["paper", "ghost", "broken", "academic", "zeta"],
    ], "the committed sequence is monotonic and ends at the working selection");

    await session.flush(4);
    assert.equal(session.callsOf("set_configs").length, 2,
      "no stale write may follow the newest one");
  } finally { session.close(); }
});

contract("GT11 theme surface: booting only reads, and an empty state says so", "pass", async () => {
  const configured = await bootGui({ themeState: THEME_STATE_A });
  try {
    assert.equal(configured.callsOf("set_configs").length, 0,
      "rendering a state must never write the configuration");
  } finally { configured.close(); }

  const empty = await bootGui({ themeState: THEME_STATE_EMPTY });
  try {
    assert.deepEqual(empty.themeRows(), [], "no installed theme means no row to offer");
    assert.equal(empty.themeEmptyVisible(), true);
    assert.deepEqual(empty.themeSummary(), { selected: "0", missing: "0", invalid: "0" });
    assert.equal(empty.callsOf("set_configs").length, 0);
  } finally { empty.close(); }
});

contract("GT12 theme surface: an unusable remembered theme warns without failing the run", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    assert.ok(session.logIssues() >= 2,
      "both unusable ids must reach the user through the log");
    assert.equal(session.logErrorCount(), 0,
      "a theme that is gone or broken is a warning, not a failed run (AGENTS section 17)");
  } finally { session.close(); }
});

contract("GT13 theme selection: a run in flight freezes the theme controls", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    const first = PLAN_ONE.items[0].source_path;
    session.window.addInputs([first]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);

    session.window.runConvert();
    await session.flush(3);

    session.themeRows().forEach(function (row) {
      assert.equal(row.disabled, true, row.id + " must not change while a run is in flight");
    });
    assert.equal(session.themeRow("ghost").removeDisabled, true);

    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(3);
    await session.resolve("set_configs", null);
    await session.flush(3);
    await session.resolve("convert", CONVERT_OK);
    await session.flush(3);

    // Only the selectable rows come back: a missing or invalid id stays unselectable,
    // while its removal button becomes usable again.
    assert.equal(session.themeRow("paper").disabled, false,
      "a run must not leave the surface frozen");
    assert.equal(session.themeRow("academic").disabled, false);
    assert.equal(session.themeRow("zeta").disabled, false);
    assert.equal(session.themeRow("ghost").disabled, true,
      "an unusable id stays unselectable after the run");
    assert.equal(session.themeRow("broken").disabled, true);
    assert.equal(session.themeRow("ghost").removeDisabled, false);
  } finally { session.close(); }
});

contract("GT14 main page: theme selection never becomes theme management", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    const actions = Array.from(session.doc.querySelectorAll("[data-theme-action]"))
      .map(function (node) { return node.getAttribute("data-theme-action"); });
    assert.deepEqual(Array.from(new Set(actions)), ["remove"],
      "the only theme action on the main page is dropping one remembered id");
    assert.equal(session.list("btn-settings"), null,
      "installing and removing themes belongs to the settings page and to phase 9B");
    assert.equal(session.list("settings-page"), null);
  } finally { session.close(); }
});
