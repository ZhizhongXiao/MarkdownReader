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

contract("GU1 bridge shape: both conversion calls use a single request", "xfail", async () => {
  const session = await bootGui();
  try {
    session.window.addInputs(["C:\\docs\\a.md"]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    session.window.runConvert();
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(3);
    await session.resolve("set_configs", null);
    await session.flush(3);

    const prepareCounts = session.argCounts("prepare_conversion");
    const convertCounts = session.argCounts("convert");
    assert.ok(prepareCounts.length !== 0, "preflight must have called prepare_conversion");
    assert.ok(convertCounts.length !== 0, "runConvert must have called convert");
    assert.deepEqual([...new Set(prepareCounts)], [1]);
    assert.deepEqual([...new Set(convertCounts)], [1]);
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

contract("GU3 terminal state: an untouched file is not a failure", "xfail", async () => {
  const session = await bootGui();
  try {
    session.window.addInputs(["C:\\docs\\a.md", "C:\\docs\\b.md"]);
    await session.flush(3);
    await session.resolve("prepare_conversion", {
      items: PLAN_TWO.items,
      warnings: [], errors: [], output_dir: "output",
      counts: PLAN_TWO.counts,
    });
    session.window.runConvert();
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_TWO);
    await session.flush(3);
    await session.resolve("set_configs", null);
    await session.flush(3);
    await session.resolve("convert", {
      success: false, files: [], errors: ["boom"], output_dir: "output",
      documents: [{ source_path: "C:\\docs\\a.md", status: "error", warnings: [] }],
    });
    await session.flush(5);

    assert.equal(session.text("stat-error"), "1",
      "only the reported failure may count as an error; the untouched file must not");
  } finally { session.close(); }
});

contract("GU4 identity: the same document added twice is still one input", "xfail", async () => {
  const session = await bootGui();
  try {
    const raw = "C:\\Docs\\x\\..\\a.md";
    session.window.addInputs([raw]);
    await session.flush(3);
    await session.resolve("prepare_conversion", {
      items: [Object.assign({}, PLAN_ONE.items[0], { source_path: raw, input_path: "C:\\Docs\\a.md" })],
      warnings: [], errors: [], output_dir: "output",
      counts: { selected: 1, directory: 0, dependency: 0, total: 1 },
    });
    await session.flush(3);
    const single = session.text("input-summary");

    // Removal already compares raw inputs with each other, so it is safe. The
    // reachable defect of string identity is here: the canonical spelling of the
    // very same document is accepted as a second input.
    session.window.addInputs(["C:\\Docs\\a.md"]);
    await session.flush(3);
    await session.resolve("prepare_conversion", PLAN_ONE);
    await session.flush(3);

    assert.equal(session.text("input-summary"), single,
      "a canonically equal path must not become a second input");
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
    assert.deepEqual(JSON.parse(call.args[0]), [first],
      "the conversion request must use the plan snapshot that was confirmed");
  } finally { session.close(); }
});

contract("GU6 log badge: the badge count matches the meaning it claims", "xfail", async () => {
  const session = await bootGui();
  try {
    session.window.log("WARNING", "earlier warning");
    session.window.addInputs(["C:\\docs\\a.md"]);
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
    let issueLines = 0;
    for (let i = 0; i < area.children.length; i += 1) {
      const line = area.children[i].textContent || "";
      if (line.indexOf("WARNING") !== -1 || line.indexOf("ERROR") !== -1) issueLines += 1;
    }
    const badge = session.text("log-issue-count");
    const label = session.list("tab-log").getAttribute("aria-label") || "";
    if (label.indexOf("个问题") !== -1) {
      assert.equal(badge, String(issueLines),
        "a badge that claims problem count must equal the problems in the log");
    }
  } finally { session.close(); }
});

contract("GU7 stats: the error stat counts documents only", "xfail", async () => {
  const session = await bootGui();
  try {
    session.window.addInputs(["C:\\docs\\a.md"]);
    await session.flush(3);
    await session.resolve("prepare_conversion", Object.assign({}, PLAN_ONE, {
      errors: ["plan problem one", "plan problem two"],
    }));
    await session.flush(3);

    assert.equal(session.text("stat-error"), "0",
      "plan messages are not failed documents");
  } finally { session.close(); }
});
