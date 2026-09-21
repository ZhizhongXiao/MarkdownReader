// Stage 6.6a - jsdom harness for the real GUI (index.html + gui.js) driven
// through a controllable pywebview stub. Test-only; no production code here.

import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error("gui harness: missing environment variable " + name);
  return value;
}

const GUI_HTML = readFileSync(requiredEnv("MR_GUI_HTML"), "utf8");
const GUI_SOURCE = readFileSync(requiredEnv("MR_GUI_JS"), "utf8").replace(/^\uFEFF/, "");

// Methods init() needs to finish; everything else stays pending until a test
// resolves it, which is what lets the contracts hold a call open and act on it.
const AUTO_RESOLVE = {
  get_templates: function () { return ["default", "modern", "office", "vscode"]; },
  get_config: function () {
    return { template: "modern", output: "output", auto_open: true,
             build_index: true, preserve_structure: false };
  },
};

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise(function (res, rej) { resolve = res; reject = rej; });
  return { promise: promise, resolve: resolve, reject: reject };
}

export class GuiSession {
  constructor(dom, window, calls, errors) {
    this.dom = dom;
    this.window = window;
    this.doc = window.document;
    this.calls = calls;
    this.errors = errors;
  }

  // ── stub accounting ──────────────────────────────────────────────
  callsOf(name) { return this.calls[name] || []; }

  pendingOf(name) {
    return this.callsOf(name).filter(function (entry) { return !entry.settled; });
  }

  argCounts(name) {
    return this.callsOf(name).map(function (entry) { return entry.args.length; });
  }

  async resolve(name, value, index) {
    const entry = this.pendingOf(name)[index || 0];
    if (!entry) throw new Error("gui harness: no pending " + name + " call to resolve");
    entry.settled = true;
    entry.deferred.resolve(value);
    await this.flush(3);
  }

  async flush(ticks) {
    const count = ticks || 1;
    for (let i = 0; i < count; i += 1) {
      await new Promise((resolve) => this.window.setTimeout(resolve, 0));
    }
  }

  async ready(limit) {
    const deadline = Date.now() + (limit || 3000);
    while (Date.now() < deadline) {
      if (this.callsOf("get_config").length !== 0) { await this.flush(3); return true; }
      await this.flush(1);
    }
    return false;
  }

  // ── DOM probes (state via the DOM, never via gui.js internals) ───
  list(id) { return this.doc.getElementById(id); }

  text(id) { const node = this.list(id); return node ? node.textContent.trim() : null; }

  conversionRows() {
    const list = this.list("conversion-list");
    if (!list) return -1;
    let count = 0;
    for (let i = 0; i < list.children.length; i += 1) {
      if (list.children[i].id !== "conversion-empty") count += 1;
    }
    return count;
  }

  logLines() { const area = this.list("log-area"); return area ? area.children.length : -1; }

  status() { return { badge: this.text("statusBadge"), text: this.text("statusText") }; }

  stats() {
    return { total: this.text("stat-total"), pending: this.text("stat-pending"),
             warning: this.text("stat-warning"), error: this.text("stat-error") };
  }

  sentinels() {
    return {
      readyState: this.doc.readyState,
      errors: this.errors.slice(),
      dropOverlay: !!this.list("drop-overlay"),
      conversionList: !!this.list("conversion-list"),
      logArea: !!this.list("log-area"),
      statusBadge: !!this.list("statusBadge"),
      templatesAsked: this.callsOf("get_templates").length,
      configAsked: this.callsOf("get_config").length,
      logLines: this.logLines(),
    };
  }

  close() { this.window.close(); }
}

export async function bootGui() {
  const dom = new JSDOM(GUI_HTML, {
    url: "http://localhost/gui/index.html",
    pretendToBeVisual: true,
    runScripts: "outside-only",
  });
  const window = dom.window;
  const errors = [];
  window.console.error = function () {
    errors.push(Array.prototype.map.call(arguments, String).join(" "));
  };

  const calls = {};
  const api = {};
  const methods = ["get_templates", "get_config", "set_configs", "prepare_conversion", "convert",
    "select_input_files", "select_input_directory", "select_output_directory",
    "open_file", "open_directory"];
  methods.forEach(function (name) {
    calls[name] = [];
    api[name] = function () {
      const args = Array.prototype.slice.call(arguments);
      const entry = { args: args, settled: false, deferred: deferred() };
      calls[name].push(entry);
      if (AUTO_RESOLVE[name]) {
        entry.settled = true;
        entry.deferred.resolve(AUTO_RESOLVE[name]());
      }
      return entry.deferred.promise;
    };
  });
  window.pywebview = { api: api };

  await new Promise(function (resolve) {
    if (window.document.readyState === "complete") { resolve(); return; }
    window.addEventListener("load", function () { resolve(); }, { once: true });
  });

  window.eval(GUI_SOURCE);
  const session = new GuiSession(dom, window, calls, errors);
  await session.ready();
  return session;
}
