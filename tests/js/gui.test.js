// Stage 6.6a - GUI behaviour contracts (G0 liveness, GU1-GU7).
//
// Every contract drives the real gui.js through its public functions and
// observes the DOM and the recorded bridge calls. Expectations are declared the
// same way as the viewer layer: "pass" must hold today, "xfail" is a strict
// known-broken contract that fails the suite if it starts passing.

import test from "node:test";
import assert from "node:assert/strict";

import { bootGui, EMPTY_THEME_INVENTORY } from "./gui_harness.mjs";

const PREPARE_SINGLE = process.env.MR_PREPARE_SINGLE_REQUEST;
const CONVERT_SINGLE = process.env.MR_CONVERT_SINGLE_REQUEST;
const IMPORT_SINGLE = process.env.MR_IMPORT_SINGLE_REQUEST;
const EXPORT_SINGLE = process.env.MR_EXPORT_SINGLE_REQUEST;

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

// Phase 9B2: an installed theme can be broken without ever having been configured. `invalid`
// stays what Phase 8C defined -- the configured ids that cannot be used today -- and the
// installation's own health arrives as a second fact, so nothing has to be redefined. `damaged`
// is installed and broken but not remembered; `paper` is installed and healthy.
const THEME_STATE_INSTALL_HEALTH = {
  default: "modern",
  installed: ["damaged", "paper"],
  configured: [],
  selected: [],
  missing: [],
  invalid: [],
  installed_invalid: ["damaged"],
  warnings: [],
};

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

contract("GT19 an installed broken theme is not selectable and cannot be removed", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_INSTALL_HEALTH });
  try {
    const damaged = session.themeRow("damaged");
    assert.equal(damaged.state, "invalid",
      "an installed theme that fails the use-time gate is not available");
    assert.equal(damaged.checked, false);
    assert.equal(damaged.disabled, true, "and it must not be selectable");
    assert.equal(damaged.removable, false,
      "it is not remembered, so offering to forget it would be a button that does nothing");

    const paper = session.themeRow("paper");
    assert.equal(paper.state, "available", "a healthy installation stays selectable");
    assert.equal(paper.disabled, false);

    assert.deepEqual(session.themeSummary(), { selected: "0", missing: "0", invalid: "1" },
      "the summary counts the rows it renders, not only the configured ones");

    session.window.toggleExternalTheme("damaged");
    await session.flush(3);
    assert.equal(session.callsOf("set_configs").length, 0,
      "a direct handler call must not select an unusable theme either");
    assert.equal(session.themeRow("damaged").state, "invalid");
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

    // The freeze is state, not only disabled controls: a direct call must not change what
    // the run is about to persist either.
    const frozenRows = JSON.stringify(session.themeRows());
    const frozenSaves = session.callsOf("set_configs").length;
    session.window.toggleExternalTheme("academic");
    session.window.removeConfiguredTheme("ghost");
    await session.flush(2);
    assert.equal(JSON.stringify(session.themeRows()), frozenRows,
      "a direct call must not move the rows while a run is in flight");
    assert.equal(session.callsOf("set_configs").length, frozenSaves,
      "a direct call must not persist anything while a run is in flight");

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
    // Phase 9B1: the settings page exists now, and installing or removing a theme lives
    // there. It stays out of the way until the user asks for it, and nothing on the main
    // page's own theme surface manages anything.
    assert.ok(session.list("btn-settings"), "the settings entry exists");
    assert.equal(session.settingsVisible(), false, "the settings page is not shown at boot");
    const mainList = session.list("external-theme-list");
    const management = Array.from(mainList.querySelectorAll("[data-theme-action]"))
      .filter(function (node) { return node.getAttribute("data-theme-action") !== "remove"; });
    assert.deepEqual(management, [], "the main page's theme list carries no management action");
  } finally { session.close(); }
});

contract("GT15 conversion waits for confirmed theme persistence", "pass", async () => {
  const first = PLAN_ONE.items[0].source_path;

  // A selection that is still being persisted holds the run back. A run reads the
  // selection back from config.json, so starting on an unconfirmed premise would either
  // lose the write or convert without the theme the user just chose.
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    session.window.addInputs([first]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);

    session.window.toggleExternalTheme("academic");
    await session.flush(2);
    assert.equal(session.callsOf("set_configs").length, 1, "the theme write is in flight");

    session.window.runConvert();
    await session.flush(3);

    assert.equal(session.callsOf("prepare_conversion").length, 1,
      "the run must not preflight while the selection is being persisted");
    assert.equal(session.callsOf("convert").length, 0, "the run must not convert yet");
    assert.equal(session.savePayloads().length, 1,
      "the run must not persist its own settings before the theme write settled");

    await session.resolve("set_configs", null);
    await session.flush(3);
    assert.equal(session.callsOf("prepare_conversion").length, 2,
      "the run starts once the selection is confirmed");
    assert.deepEqual(Object.keys(session.savePayloads()[0]), ["external_themes"],
      "the theme write is the first thing that lands");

    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(2);
    assert.ok(session.savePayloads()[1] && session.savePayloads()[1].template,
      "the run persists its own settings only after the theme write settled");
    await session.resolve("set_configs", null);
    await session.flush(2);
    await session.resolve("convert", CONVERT_OK);
    await session.flush(2);
    assert.equal(session.callsOf("convert").length, 1);
  } finally { session.close(); }

  // A selection that could not be persisted cancels the run: the choice the user just
  // made is not in effect, so converting would silently use the old configuration.
  const cancelled = await bootGui({ autoThemeState: false });
  try {
    await cancelled.resolve("get_theme_state", THEME_STATE_A);
    cancelled.window.addInputs([first]);
    await cancelled.flush(3);
    await cancelled.resolve("prepare_conversion", PLAN_ONE);

    cancelled.window.toggleExternalTheme("academic");
    await cancelled.flush(2);
    cancelled.window.runConvert();
    await cancelled.flush(2);
    await cancelled.reject("set_configs", new Error("boom"));
    await cancelled.flush(2);
    await cancelled.resolve("get_theme_state", THEME_STATE_A);
    await cancelled.flush(3);

    assert.equal(cancelled.callsOf("prepare_conversion").length, 1,
      "a cancelled run must not preflight");
    assert.equal(cancelled.callsOf("convert").length, 0, "a cancelled run must not convert");
    assert.equal(cancelled.savePayloads().length, 1,
      "a cancelled run must not persist its own settings");
    assert.ok(cancelled.logErrorCount() >= 2,
      "the refused save and the cancellation are both reported");
    assert.equal(cancelled.doc.querySelector(".btn-run").disabled, false,
      "the conversion lock is released when the run is cancelled");
    assert.equal(cancelled.themeRow("academic").checked, false,
      "the surface shows the bridge state again, not the assumption");

    cancelled.window.toggleExternalTheme("zeta");
    await cancelled.flush(2);
    assert.equal(cancelled.callsOf("set_configs").length, 2,
      "the surface stays usable after a cancelled run");
    await cancelled.resolve("set_configs", null);
  } finally { cancelled.close(); }
});

contract("GT16 summary: the selected count follows the working selection", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A });
  try {
    assert.deepEqual(session.themeSummary(), { selected: "1", missing: "1", invalid: "1" });

    session.window.toggleExternalTheme("academic");
    await session.flush(2);
    assert.deepEqual(session.themeSummary(), { selected: "2", missing: "1", invalid: "1" },
      "checking a theme is visible in the summary before the bridge answers");

    await session.resolve("set_configs", null);
    session.window.toggleExternalTheme("paper");
    await session.flush(2);
    assert.deepEqual(session.themeSummary(), { selected: "1", missing: "1", invalid: "1" },
      "unchecking a theme is visible in the summary too");
    await session.resolve("set_configs", null);
  } finally { session.close(); }
});

contract("GT17 a refused save discards the queued intent and rebuilds from the bridge", "pass", async () => {
  const session = await bootGui({ autoThemeState: false });
  try {
    await session.resolve("get_theme_state", THEME_STATE_A);
    session.window.toggleExternalTheme("academic");
    await session.flush(2);
    session.window.toggleExternalTheme("zeta");
    await session.flush(2);
    assert.equal(session.callsOf("set_configs").length, 1,
      "the second change is held back while the first write is in flight");

    await session.reject("set_configs", new Error("boom"));
    await session.flush(2);
    assert.equal(session.callsOf("get_theme_state").length, 2,
      "a refused save asks the bridge what is true");

    await session.resolve("get_theme_state", THEME_STATE_EMPTY);
    await session.flush(3);
    assert.equal(session.callsOf("set_configs").length, 1,
      "the queued intent is discarded rather than retried");
    assert.deepEqual(themeIdList(session.themeRows()), [],
      "the optimistic state is fully replaced by the bridge state");
    await session.flush(3);
    assert.equal(session.callsOf("set_configs").length, 1, "and nothing is sent afterwards");
  } finally { session.close(); }
});

contract("GT18 a failed refetch falls back to the last persisted selection", "pass", async () => {
  const session = await bootGui({ autoThemeState: false });
  try {
    await session.resolve("get_theme_state", THEME_STATE_B);
    session.window.toggleExternalTheme("zeta");
    await session.flush(2);
    assert.deepEqual(Array.from(session.savePayloads()[0].external_themes),
      ["paper", "academic", "ghost", "broken", "zeta"]);
    await session.resolve("set_configs", null);
    await session.flush(2);

    session.window.toggleExternalTheme("academic");
    await session.flush(2);
    await session.reject("set_configs", new Error("boom"));
    await session.flush(2);
    await session.reject("get_theme_state", new Error("bridge down"));
    await session.flush(3);

    assert.deepEqual(themeIdList(session.themeRows()),
      ["academic", "broken", "ghost", "paper", "zeta"]);
    assert.equal(session.themeRow("academic").checked, true,
      "academic came back: a save that succeeded had persisted it");
    assert.equal(session.themeRow("zeta").checked, true, "so did zeta");
    assert.ok(session.logErrorCount() >= 2, "both failures are reported");
    assert.equal(session.callsOf("set_configs").length, 2, "no third write is attempted");
    await session.flush(3);

    session.window.toggleExternalTheme("academic");
    await session.flush(2);
    assert.equal(session.callsOf("set_configs").length, 3,
      "the queue is not left stuck after a failed refetch");
    await session.resolve("set_configs", null);
  } finally { session.close(); }
});

// ── Phase 9B1: the settings surface (GS1-GS13 + GS2b, 14 records) ─────────────
//
// The settings page owns a different fact than the main page (AGENTS section 17): the
// main page reads which installed themes a document carries, the settings page reads
// what is installed and whether it still works. The two must never stand in for each
// other, so the fixtures below deliberately separate them.

const THEME_INVENTORY = {
  installed: [
    { id: "paper", valid: true, reason: null },
    { id: "zeta", valid: true, reason: null },
    // Installed and broken, but *not* a configured id, so it cannot appear in
    // THEME_STATE_A.invalid - that list only covers what the configuration remembers.
    { id: "damaged", valid: false, reason: "外置主题 CSS 不合法：damaged" },
  ],
  root: "C:\\data\\assets\\themes\\external",
  template_root: "C:\\app\\themes\\template",
  warnings: [],
};

const STORAGE_INFO = {
  mode: "onedir",
  user_data_root: "C:\\data",
  config_path: "C:\\data\\profile\\config.json",
  external_themes_root: "C:\\data\\assets\\themes\\external",
  runtime_root: "C:\\data\\runtime",
  runtime_note: "预留：日志与 WebView2 尚未迁入。",
};

const ABOUT_INFO = {
  name: "MarkdownReader",
  version: "1.0.0rc1",
  renderer_version: "v2",
  python: "3.12.10",
  mode: "onedir",
};

// What the bridge reports after `zeta` was uninstalled: the memory keeps the id, so the
// main page must show it as missing instead of keeping it selectable.
const THEME_STATE_AFTER_REMOVE = Object.assign({}, THEME_STATE_A, {
  installed: ["academic", "broken", "paper"],
  configured: ["paper", "ghost", "broken", "zeta"],
  missing: ["ghost", "zeta"],
  warnings: ["外置主题当前未安装：ghost", "外置主题当前未安装：zeta"],
});

contract("GS1 settings shell: the entry opens the page and back returns intact", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY });
  try {
    assert.equal(session.settingsVisible(), false, "the settings page starts hidden");
    const summaryBefore = session.themeSummary();
    const tabBefore = session.doc.querySelector(".workspace-tab.active").id;

    session.window.openSettings();
    await session.flush(4);
    assert.equal(session.settingsVisible(), true, "the entry opens the settings page");

    session.window.closeSettings();
    await session.flush(4);
    assert.equal(session.settingsVisible(), false, "back returns to the main page");
    assert.equal(session.doc.querySelector(".workspace-tab.active").id, tabBefore,
      "the workspace tab the user was on survives the trip");
    assert.deepEqual(session.themeSummary(), summaryBefore,
      "the carry-set summary is the same after a settings visit");
  } finally { session.close(); }
});

contract("GS2 the settings inventory reports validity per installed theme", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY });
  try {
    assert.equal(THEME_STATE_A.invalid.indexOf("damaged"), -1,
      "fixture: damaged is installed but is not a configured id");

    session.window.openSettings();
    await session.flush(4);

    assert.deepEqual(session.inventoryIds(), ["damaged", "paper", "zeta"],
      "every installed theme is listed, healthy or not");
    assert.equal(session.inventoryRow("paper").valid, true);
    assert.equal(session.inventoryRow("damaged").valid, false,
      "an installed theme that fails validation must not be reported as healthy");
    assert.ok(session.inventoryRow("damaged").reason.indexOf("damaged") !== -1,
      "the refusal is shown on the row instead of being swallowed");
  } finally { session.close(); }
});

contract("GS2b the settings inventory is read from the bridge, not from the carry set", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY });
  try {
    assert.equal(session.callsOf("get_theme_inventory").length, 0,
      "the inventory is not fetched before the settings page is opened");
    session.window.openSettings();
    await session.flush(4);
    assert.equal(session.callsOf("get_theme_inventory").length, 1,
      "opening the settings page asks the bridge for the installation facts");
  } finally { session.close(); }
});

contract("GS3 importing a theme goes through the bridge and never rewrites the carry set", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY });
  try {
    session.window.openSettings();
    await session.flush(4);

    session.window.importTheme();
    await session.flush(3);
    assert.equal(session.callsOf("import_theme").length, 1, "the import goes through the bridge");
    // The request is compared as JSON: the answer's args are objects from the page's own
    // realm, so a strict deep-equal against a Node literal would compare prototypes.
    assert.equal(JSON.stringify(session.callsOf("import_theme")[0].args), "[{}]",
      "the bridge owns the source dialog, so the page sends an empty request");

    await session.resolve("import_theme", { ok: true, id: "damaged", error: "" });
    await session.flush(3);
    assert.equal(session.callsOf("get_theme_inventory").length, 2,
      "a successful import re-reads the inventory instead of guessing");
    assert.equal(session.callsOf("set_configs").length, 0,
      "installing a theme is not a selection change");
  } finally { session.close(); }
});

contract("GS4 a refused import is reported and leaves the page usable", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY });
  try {
    session.window.openSettings();
    await session.flush(4);
    const issuesBefore = session.logIssues();

    session.window.importTheme();
    await session.flush(3);
    await session.resolve("import_theme",
      { ok: false, id: "", error: "主题模板缺失：C:\\app\\themes\\template" });
    await session.flush(3);
    assert.ok(session.logIssues() > issuesBefore, "the refusal is reported to the user");
    assert.equal(session.callsOf("get_theme_inventory").length, 1,
      "a refusal must not pretend the inventory changed");
    assert.deepEqual(session.inventoryIds(), ["damaged", "paper", "zeta"], "the list is unchanged");

    // A bridge that fails instead of answering must not leave the page stuck either.
    session.window.importTheme();
    await session.flush(3);
    await session.reject("import_theme", new Error("bridge down"));
    await session.flush(3);
    assert.ok(session.logIssues() > issuesBefore, "a failed import is reported too");

    session.window.importTheme();
    await session.flush(3);
    assert.equal(session.callsOf("import_theme").length, 3, "the page is still usable afterwards");
    await session.resolve("import_theme", { ok: true, id: "paper", error: "" });
  } finally { session.close(); }
});

contract("GS5 removing an installed theme never rewrites the carry set", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY });
  try {
    session.window.openSettings();
    await session.flush(4);

    session.window.removeInstalledTheme("zeta");
    await session.flush(3);
    assert.deepEqual(session.callsOf("remove_theme")[0].args, ["zeta"], "the row's own id is sent");

    await session.resolve("remove_theme", { ok: true, id: "zeta", error: "" });
    await session.flush(3);
    assert.equal(session.callsOf("get_theme_inventory").length, 2, "the list is re-read after a removal");
    assert.equal(session.callsOf("set_configs").length, 0,
      "uninstalling is not unchecking: the memory keeps the id and the main page says missing");
  } finally { session.close(); }
});

contract("GS6 exporting the template reports the path and surfaces a refusal", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY });
  try {
    session.window.openSettings();
    await session.flush(4);
    const linesBefore = session.logLines();

    session.window.exportThemeTemplate();
    await session.flush(3);
    assert.equal(JSON.stringify(session.callsOf("export_theme_template")[0].args), "[{}]",
      "the bridge owns the destination dialog");
    await session.resolve("export_theme_template",
      { ok: true, path: "C:\\out\\markdownreader-theme-template", error: "" });
    await session.flush(3);
    assert.ok(session.logLines() > linesBefore, "the written path is reported");

    const issuesAfterSuccess = session.logIssues();
    session.window.exportThemeTemplate();
    await session.flush(3);
    await session.resolve("export_theme_template",
      { ok: false, path: "", error: "导出目标已存在：C:\\out\\markdownreader-theme-template" });
    await session.flush(3);
    assert.ok(session.logIssues() > issuesAfterSuccess,
      "a refused export is reported instead of looking like a success");
  } finally { session.close(); }
});

contract("GS7 opening the theme location works on a fresh installation", "pass", async () => {
  const session = await bootGui({
    themeState: THEME_STATE_EMPTY, themeInventory: EMPTY_THEME_INVENTORY,
  });
  try {
    session.window.openSettings();
    await session.flush(4);
    assert.equal(session.settingsVisible(), true);
    assert.deepEqual(session.inventoryIds(), [], "a fresh installation has nothing installed");

    session.window.openThemeLocation();
    await session.flush(3);
    assert.equal(session.callsOf("open_theme_location").length, 1,
      "the page asks the bridge to create-and-open, not the system to reveal a bare path");

    const issuesBefore = session.logIssues();
    await session.resolve("open_theme_location",
      { ok: false, path: "", error: "无法创建主题目录：C:\\data" });
    await session.flush(3);
    assert.ok(session.logIssues() > issuesBefore,
      "a directory that cannot be created is reported instead of silently doing nothing");
  } finally { session.close(); }
});

contract("GS8 storage information renders the bridge facts verbatim", "pass", async () => {
  const session = await bootGui({
    themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY, storageInfo: STORAGE_INFO,
  });
  try {
    session.window.openSettings();
    await session.flush(4);

    const facts = session.facts("settings-storage");
    assert.ok(facts, "the settings page carries a storage section");
    assert.equal(facts.mode, STORAGE_INFO.mode);
    assert.equal(facts.user_data_root, STORAGE_INFO.user_data_root);
    assert.equal(facts.config_path, STORAGE_INFO.config_path);
    assert.equal(facts.external_themes_root, STORAGE_INFO.external_themes_root);
    assert.equal(facts.runtime_root, STORAGE_INFO.runtime_root);
  } finally { session.close(); }
});

contract("GS9 about renders the bridge facts verbatim", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, aboutInfo: ABOUT_INFO });
  try {
    session.window.openSettings();
    await session.flush(4);

    const facts = session.facts("settings-about");
    assert.ok(facts, "the settings page carries an about section");
    assert.equal(facts.name, ABOUT_INFO.name);
    assert.equal(facts.version, ABOUT_INFO.version,
      "the version is the bridge's fact, not a number baked into the page");
    assert.equal(facts.renderer_version, ABOUT_INFO.renderer_version);
  } finally { session.close(); }
});

contract("GS10 theme management is locked while a conversion runs", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY });
  try {
    session.window.addInputs([PLAN_ONE.items[0].source_path]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    session.window.openSettings();
    await session.flush(4);
    assert.equal(session.list("btn-import-theme").disabled, false, "management works while idle");

    session.window.runConvert();
    await session.flush(3);
    assert.equal(session.list("btn-import-theme").disabled, true, "a run locks the management actions");
    assert.equal(session.list("btn-export-theme-template").disabled, true);
    assert.equal(session.list("btn-open-theme-location").disabled, true);
    assert.equal(session.inventoryRow("paper").removeDisabled, true);

    const frozen = JSON.stringify(session.inventoryRows());
    session.window.importTheme();
    session.window.removeInstalledTheme("paper");
    session.window.exportThemeTemplate();
    session.window.openThemeLocation();
    await session.flush(3);
    assert.equal(session.callsOf("import_theme").length, 0,
      "a direct call must not reach the bridge while a run is in flight");
    assert.equal(session.callsOf("remove_theme").length, 0);
    assert.equal(session.callsOf("export_theme_template").length, 0);
    assert.equal(session.callsOf("open_theme_location").length, 0);
    assert.equal(JSON.stringify(session.inventoryRows()), frozen, "and nothing moves on the page");

    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(2);
    await session.resolve("set_configs", null);
    await session.flush(2);
    await session.resolve("convert", CONVERT_OK);
    await session.flush(3);
    assert.equal(session.list("btn-import-theme").disabled, false,
      "the run must not leave the management surface locked");
  } finally { session.close(); }
});

contract("GS11 no settings action ever writes the carry set", "pass", async () => {
  const session = await bootGui({ themeState: THEME_STATE_A, themeInventory: THEME_INVENTORY });
  try {
    session.window.openSettings();
    await session.flush(4);

    session.window.importTheme();
    await session.flush(2);
    await session.resolve("import_theme", { ok: true, id: "paper", error: "" });
    session.window.removeInstalledTheme("zeta");
    await session.flush(2);
    await session.resolve("remove_theme", { ok: true, id: "zeta", error: "" });
    session.window.exportThemeTemplate();
    await session.flush(2);
    await session.resolve("export_theme_template", { ok: true, path: "C:\\out\\t", error: "" });
    session.window.openThemeLocation();
    await session.flush(2);
    await session.resolve("open_theme_location", { ok: true, path: "C:\\data", error: "" });
    await session.flush(3);

    assert.equal(session.callsOf("set_configs").length, 0,
      "the settings surface never persists: that write belongs to the main page");
    assert.deepEqual(session.savePayloads(), []);
  } finally { session.close(); }
});

contract("GS12 returning from settings re-reads the state before it reveals the main page", "pass", async () => {
  const session = await bootGui({ autoThemeState: false, themeInventory: THEME_INVENTORY });
  try {
    await session.resolve("get_theme_state", THEME_STATE_A);
    await session.flush(3);
    assert.equal(session.themeRow("zeta").state, "available", "fixture: zeta starts selectable");

    // Remembering zeta is what makes its later disappearance visible as `missing`.
    session.window.toggleExternalTheme("zeta");
    await session.flush(2);
    await session.resolve("set_configs", null);
    await session.flush(2);

    session.window.openSettings();
    await session.flush(4);
    session.window.removeInstalledTheme("zeta");
    await session.flush(2);
    await session.resolve("remove_theme", { ok: true, id: "zeta", error: "" });
    await session.flush(3);

    // Phase 1: while the re-read is in flight the settings page must stay in front. Revealing
    // the main page here would hand the user rows this GUI already knows are stale.
    session.window.closeSettings();
    await session.flush(2);
    assert.equal(session.callsOf("get_theme_state").length, 2,
      "closing re-reads what a document can carry");
    assert.equal(session.pendingOf("get_theme_state").length, 1, "the re-read is still in flight");
    assert.equal(session.settingsVisible(), true,
      "the main page must not be revealed before the new state arrives");
    assert.equal(session.list("btn-settings-back").disabled, true, "a second Back is refused");
    assert.equal(session.list("btn-import-theme").disabled, true,
      "management stays frozen while the page is closing");

    session.window.closeSettings();
    await session.flush(2);
    assert.equal(session.callsOf("get_theme_state").length, 2, "one close starts one re-read");

    // Phase 2: the state arrives and only then does the main page appear -- already correct.
    await session.resolve("get_theme_state", THEME_STATE_AFTER_REMOVE);
    await session.flush(3);
    assert.equal(session.settingsVisible(), false, "the page closes once the state is known");
    assert.equal(session.themeRow("zeta").state, "missing",
      "the main page shows the new state at the moment it appears");
    assert.equal(session.list("btn-settings-back").disabled, false);
    assert.equal(session.list("btn-import-theme").disabled, false,
      "closing must not leave the management surface locked");

    // Phase 3: a failed re-read keeps the settings page in front instead of exposing a main
    // page this GUI cannot vouch for, and Back stays a real retry.
    session.window.openSettings();
    await session.flush(4);
    const failuresBefore = session.logErrorCount();
    session.window.closeSettings();
    await session.flush(2);
    await session.reject("get_theme_state", new Error("bridge down"));
    await session.flush(3);
    assert.equal(session.settingsVisible(), true,
      "a failed re-read must not reveal a stale main page");
    assert.ok(session.logErrorCount() > failuresBefore, "the failure is reported");
    assert.equal(session.list("btn-settings-back").disabled, false, "Back can be pressed again");

    session.window.closeSettings();
    await session.flush(2);
    assert.equal(session.callsOf("get_theme_state").length, 4, "the retry really re-reads");
    await session.resolve("get_theme_state", THEME_STATE_AFTER_REMOVE);
    await session.flush(3);
    assert.equal(session.settingsVisible(), false, "the retry closes the page");
  } finally { session.close(); }
});

contract("GS13 the settings bridge calls keep the single-request shape", "pass", async () => {
  // The joint half of the shape contract: the JS call and the Python signature are
  // measured in different places (pytest measures the signature and hands the answer in).
  assert.equal(IMPORT_SINGLE, "1",
    "BridgeApi.import_theme must be (self, request) so the bridge owns the source dialog");
  assert.equal(EXPORT_SINGLE, "1",
    "BridgeApi.export_theme_template must be (self, request) as well");
});

// ── Phase 11: terminal removal of MarkdownReader user data ──────────────────────
//
// The page presents and asks; it never deletes. `get_storage_info()` decides whether the
// action exists at all (onefile only) and which three things it promises, and the
// confirmation sends exactly one request -- after which the bridge ends the window and the
// filesystem work happens in the application, not here.

const STORAGE_INFO_SOURCE = {
  mode: "source",
  user_data_root: "U:/repo/.runtime",
  config_path: "U:/repo/.runtime/profile/config.json",
  external_themes_root: "U:/repo/.runtime/assets/themes/external",
  runtime_root: "U:/repo/.runtime/runtime",
  runtime_note: "source 布局的运行时数据。",
  removal_available: false,
  removal_items: [],
};

const STORAGE_INFO_ONEDIR = Object.assign({}, STORAGE_INFO_SOURCE, {
  mode: "onedir",
  user_data_root: "C:/app/MarkdownReader/data",
  config_path: "C:/app/MarkdownReader/data/profile/config.json",
  external_themes_root: "C:/app/MarkdownReader/data/assets/themes/external",
  runtime_root: "C:/app/MarkdownReader/data/runtime",
  runtime_note: "删除整个程序目录即可完整移除。",
});

const ONEFILE_ROOT = "C:/Users/u/AppData/Local/MarkdownReader";

const STORAGE_INFO_ONEFILE = {
  mode: "onefile",
  user_data_root: ONEFILE_ROOT,
  config_path: ONEFILE_ROOT + "/profile/config.json",
  external_themes_root: ONEFILE_ROOT + "/assets/themes/external",
  runtime_root: ONEFILE_ROOT + "/runtime",
  runtime_note: "日志与 WebView2 profile 都在 runtime 内；移除用户数据仅 onefile 提供。",
  removal_available: true,
  removal_items: [
    { key: "config", label: "配置", path: ONEFILE_ROOT + "/profile/config.json" },
    { key: "external-themes", label: "外置主题", path: ONEFILE_ROOT + "/assets" },
    { key: "runtime", label: "runtime 数据", path: ONEFILE_ROOT + "/runtime" },
  ],
};

// Every removal contract drives frozen time: the countdown is five seconds, and waiting for
// it would make the suite slow and flaky in equal measure.
async function bootRemoval(storageInfo) {
  const session = await bootGui({
    clock: true,
    themeState: THEME_STATE_A,
    themeInventory: THEME_INVENTORY,
    storageInfo: storageInfo,
  });
  session.window.openSettings();
  await session.flush(4);
  return session;
}

function promisedItems(session) {
  const modal = session.list("user-data-confirm");
  if (!modal) return null;
  return Array.prototype.map.call(modal.querySelectorAll("[data-removal-item]"), function (node) {
    return node.getAttribute("data-removal-item");
  });
}

// Red reads as a missing capability, not as a broken probe: the entry is asserted before it is
// used, so a page without the removal surface fails on that fact instead of on a null deref.
function removalEntry(session) {
  const entry = session.list("btn-remove-user-data");
  assert.ok(entry, "the removal entry must exist before a confirmation can be opened");
  return entry;
}

// jsdom runs no inline event handlers (`runScripts: "outside-only"`), so these contracts drive
// the page's own functions -- exactly how the settings contracts drive `openSettings()`.
function openRemovalConfirmation(session) {
  const entry = removalEntry(session);
  assert.equal(entry.disabled, false, "the entry is offered while nothing is in flight");
  session.window.openUserDataConfirmation();
}

contract("GR1 the removal entry exists only when the bridge offers it", "pass", async () => {
  const onefile = await bootRemoval(STORAGE_INFO_ONEFILE);
  try {
    const entry = onefile.list("btn-remove-user-data");
    assert.ok(entry, "onefile must offer the removal entry");
    assert.equal(entry.hidden, false, "the entry is offered on onefile");
  } finally { onefile.close(); }

  const cases = [["source", STORAGE_INFO_SOURCE], ["onedir", STORAGE_INFO_ONEDIR]];
  for (let i = 0; i < cases.length; i += 1) {
    const session = await bootRemoval(cases[i][1]);
    try {
      const entry = session.list("btn-remove-user-data");
      const offered = !!entry && entry.hidden !== true && !entry.classList.contains("hidden");
      assert.equal(offered, false, cases[i][0] + " must not offer removing user data");
      assert.equal(session.callsOf("request_user_data_removal").length, 0,
        "and nothing may be requested there either");
    } finally { session.close(); }
  }
});

contract("GR2 the confirmation lists exactly what the bridge promises", "pass", async () => {
  const session = await bootRemoval(STORAGE_INFO_ONEFILE);
  try {
    openRemovalConfirmation(session);
    await session.flush(4);

    const modal = session.list("user-data-confirm");
    assert.ok(modal, "the confirmation must exist");
    assert.equal(modal.classList.contains("hidden"), false, "the confirmation is shown");
    assert.deepEqual((promisedItems(session) || []).slice().sort(),
      ["config", "external-themes", "runtime"],
      "the three promised facts, and only those, come from the bridge reply");
    assert.ok(modal.textContent.indexOf(STORAGE_INFO_ONEFILE.config_path) !== -1,
      "the configuration path is named");
    assert.ok(modal.textContent.indexOf(STORAGE_INFO_ONEFILE.runtime_root) !== -1,
      "the runtime path is named");
  } finally { session.close(); }
});

contract("GR3 the confirmation stays disabled for the full five seconds", "pass", async () => {
  const session = await bootRemoval(STORAGE_INFO_ONEFILE);
  try {
    openRemovalConfirmation(session);
    await session.flush(4);

    const confirm = session.list("btn-user-data-confirm");
    assert.ok(confirm, "the confirmation has a confirm button");
    assert.equal(confirm.disabled, true, "it is disabled when the confirmation appears");

    await session.advance(4999);
    assert.equal(confirm.disabled, true, "still disabled before five seconds have passed");

    await session.advance(1);
    assert.equal(confirm.disabled, false, "enabled once the countdown has finished");
  } finally { session.close(); }
});

contract("GR4 cancel is always available and reopening restarts the countdown", "pass", async () => {
  const session = await bootRemoval(STORAGE_INFO_ONEFILE);
  try {
    openRemovalConfirmation(session);
    await session.flush(4);

    const cancel = session.list("btn-user-data-cancel");
    assert.ok(cancel, "the confirmation has a cancel button");
    assert.equal(cancel.disabled, false, "cancel works while the countdown still runs");

    await session.advance(6000);
    assert.equal(session.list("btn-user-data-confirm").disabled, false, "the countdown finished");
    session.window.cancelUserDataRemoval();
    await session.flush(3);

    assert.equal(session.list("user-data-confirm").classList.contains("hidden"), true,
      "cancel closes the confirmation");
    assert.equal(session.callsOf("request_user_data_removal").length, 0,
      "cancel never asks the bridge for anything");

    openRemovalConfirmation(session);
    await session.flush(3);
    assert.equal(session.list("btn-user-data-confirm").disabled, true,
      "reopening restarts the countdown instead of keeping the finished one");
    await session.advance(4999);
    assert.equal(session.list("btn-user-data-confirm").disabled, true);
    await session.advance(1);
    assert.equal(session.list("btn-user-data-confirm").disabled, false);
  } finally { session.close(); }
});

contract("GR5 confirming locks the page and asks the bridge exactly once", "pass", async () => {
  const session = await bootRemoval(STORAGE_INFO_ONEFILE);
  try {
    session.window.addInputs([PLAN_ONE.items[0].source_path]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);

    openRemovalConfirmation(session);
    await session.flush(4);
    await session.advance(5000);
    session.window.confirmUserDataRemoval();
    await session.flush(4);

    assert.equal(session.callsOf("request_user_data_removal").length, 1,
      "the terminal transition is requested exactly once");
    assert.equal(session.list("btn-import-theme").disabled, true,
      "the terminal state locks the management actions before any reply arrives");

    // A disabled button is a hint, not a rule: the direct calls must be refused as well.
    session.window.importTheme();
    session.window.openThemeLocation();
    session.window.runConvert();
    await session.flush(4);
    assert.equal(session.callsOf("import_theme").length, 0, "a direct management call is refused");
    assert.equal(session.callsOf("open_theme_location").length, 0,
      "including the one that creates directories");
    assert.equal(session.callsOf("set_configs").length, 0,
      "no run may write configuration after the terminal flag");
    assert.equal(session.callsOf("convert").length, 0, "and no run may start");

    session.window.confirmUserDataRemoval();
    await session.flush(3);
    assert.equal(session.callsOf("request_user_data_removal").length, 1,
      "a second confirmation must not ask twice");
  } finally { session.close(); }
});

contract("GR6 removing user data uses no other bridge call", "pass", async () => {
  const session = await bootRemoval(STORAGE_INFO_ONEFILE);
  try {
    openRemovalConfirmation(session);
    await session.flush(4);
    await session.advance(5000);
    session.window.confirmUserDataRemoval();
    await session.flush(4);

    ["set_configs", "import_theme", "remove_theme", "export_theme_template",
      "open_theme_location", "convert"].forEach(function (name) {
      assert.equal(session.callsOf(name).length, 0,
        name + " must not be part of removing user data");
    });
    assert.deepEqual(session.argCounts("request_user_data_removal"), [0],
      "the request carries no target: the backend decides what user data means");
  } finally { session.close(); }
});

contract("GR7 an explicit refusal reopens the page instead of locking it", "pass", async () => {
  // The backend is the authority, and it may answer `{ok: false}` -- something was still in
  // flight. The page holds a provisional lock while the reply travels, but a structured refusal
  // has to hand the session back: otherwise the user is locked out of a window that will never
  // close, which is the opposite of what the refusal means.
  const session = await bootRemoval(STORAGE_INFO_ONEFILE);
  try {
    session.window.addInputs([PLAN_ONE.items[0].source_path]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);

    openRemovalConfirmation(session);
    await session.flush(4);
    await session.advance(5000);
    session.window.confirmUserDataRemoval();
    await session.flush(4);
    assert.equal(session.callsOf("request_user_data_removal").length, 1,
      "the first confirmation asks once");
    assert.equal(session.list("btn-import-theme").disabled, true,
      "the provisional lock holds while the reply is pending");

    await session.resolve("request_user_data_removal", { ok: false, error: "operation in flight" });
    await session.flush(4);

    assert.equal(session.list("user-data-confirm").classList.contains("hidden"), false,
      "a refusal keeps the confirmation visible");
    assert.equal(session.list("btn-import-theme").disabled, false,
      "the page works again once the backend refuses");
    assert.equal(session.list("btn-settings-back").disabled, false);
    assert.equal(session.list("btn-user-data-confirm").disabled, false,
      "no second countdown is needed: the confirmation gate was already passed");

    session.window.confirmUserDataRemoval();
    await session.flush(4);
    assert.equal(session.callsOf("request_user_data_removal").length, 2,
      "the retry really asks the backend again");
  } finally { session.close(); }
});
