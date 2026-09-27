// Stage 6.6a - jsdom harness for the real GUI (index.html + gui.js) driven
// through a controllable pywebview stub. Test-only; no production code here.
// Phase 9A adds the external theme surface: its state is a bridge reply like every
// other fact on the page, so the harness owns that reply and a contract can hand the
// page any state it needs to render.

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

// A fresh installation: no user theme is installed or remembered. It is the default
// theme-state reply so the contracts that are not about themes keep the behaviour
// they had before this surface existed.
export const EMPTY_THEME_STATE = {
  default: "modern",
  installed: [],
  configured: [],
  selected: [],
  missing: [],
  invalid: [],
  warnings: [],
};

// Phase 9B1: the settings surface reads three other facts. They are requested lazily
// (only when the settings page opens), so the samples below exist to keep that page
// renderable, not to describe a real machine - a contract that cares about the values
// hands its own fixture in.
export const EMPTY_THEME_INVENTORY = {
  installed: [],
  root: "",
  template_root: "",
  warnings: [],
};

export const STORAGE_INFO_SAMPLE = {
  mode: "source",
  user_data_root: "",
  config_path: "",
  external_themes_root: "",
  runtime_root: "",
  runtime_note: "",
};

export const ABOUT_INFO_SAMPLE = {
  name: "MarkdownReader",
  version: "0.0.0-test",
  renderer_version: "v2",
  python: "3.12",
  mode: "source",
};

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise(function (res, rej) { resolve = res; reject = rej; });
  return { promise: promise, resolve: resolve, reject: reject };
}

export class GuiSession {
  constructor(dom, window, calls, errors, options) {
    this.dom = dom;
    this.window = window;
    this.doc = window.document;
    this.calls = calls;
    this.errors = errors;
    this.options = options || {};
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
    // A real bridge serialises its reply, so the page never receives the very
    // object a test holds. Copying here keeps fixture objects immutable across
    // contracts - otherwise one contract status update leaks into the next.
    const reply = value === null || value === undefined
      ? value
      : JSON.parse(JSON.stringify(value));
    entry.deferred.resolve(reply);
    await this.flush(3);
  }

  async reject(name, error, index) {
    const entry = this.pendingOf(name)[index || 0];
    if (!entry) throw new Error("gui harness: no pending " + name + " call to reject");
    entry.settled = true;
    entry.deferred.reject(error instanceof Error ? error : new Error(String(error)));
    await this.flush(3);
  }

  async flush(ticks) {
    const count = ticks || 1;
    for (let i = 0; i < count; i += 1) {
      await new Promise((resolve) => this.window.setTimeout(resolve, 0));
    }
  }

  // init() ends after the configuration *and* the theme state reply, because the theme
  // surface is rendered from the bridge rather than from a constant. A contract that
  // deliberately keeps that reply open (autoThemeState: false) opts out of the second
  // wait instead of spinning out the deadline here.
  async ready(limit) {
    const deadline = Date.now() + (limit || 3000);
    while (Date.now() < deadline) {
      if (this.callsOf("get_config").length !== 0) break;
      await this.flush(1);
    }
    if (this.callsOf("get_config").length === 0) return false;

    if (this.options.autoThemeState !== false) {
      const themeDeadline = Date.now() + (limit || 3000);
      while (Date.now() < themeDeadline) {
        const themeCalls = this.callsOf("get_theme_state");
        if (themeCalls.length !== 0 && themeCalls.every(function (entry) { return entry.settled; })) {
          break;
        }
        await this.flush(1);
      }
    }
    await this.flush(3);
    return true;
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

  // Log lines that are actually issues, counted from the DOM so a contract
  // never has to read the GUI internals.
  logIssues() {
    const area = this.list("log-area");
    if (!area) return -1;
    let count = 0;
    for (let i = 0; i < area.children.length; i += 1) {
      // The level is a class on the line, the message is its text.
      const cls = area.children[i].classList;
      if (cls.contains("log-warn") || cls.contains("log-err")) count += 1;
    }
    return count;
  }

  status() { return { badge: this.text("statusBadge"), text: this.text("statusText") }; }

  stats() {
    return { total: this.text("stat-total"), pending: this.text("stat-pending"),
             warning: this.text("stat-warning"), error: this.text("stat-error") };
  }

  // ── theme selection probes (DOM only, like every probe above) ─────────────
  // Rows are the list's own children that carry an id; the checkbox and the remove
  // button are found inside them, so the markup may put the label anywhere.
  themeRows() {
    const list = this.list("external-theme-list");
    if (!list) return null;
    const rows = [];
    for (let i = 0; i < list.children.length; i += 1) {
      const row = list.children[i];
      const id = row.getAttribute ? row.getAttribute("data-theme-id") : null;
      if (!id) continue;
      const box = row.querySelector('input[type="checkbox"]');
      const remove = row.querySelector('[data-theme-action="remove"]');
      rows.push({
        id: id,
        state: row.getAttribute("data-theme-state"),
        checked: box ? box.checked : null,
        disabled: box ? box.disabled : null,
        removable: !!remove,
        removeDisabled: remove ? remove.disabled : null,
      });
    }
    return rows;
  }

  themeRow(id) {
    const rows = this.themeRows() || [];
    for (let i = 0; i < rows.length; i += 1) {
      if (rows[i].id === id) return rows[i];
    }
    return null;
  }

  themeSummary() {
    const node = this.list("external-theme-summary");
    if (!node) return null;
    return {
      selected: node.getAttribute("data-selected"),
      missing: node.getAttribute("data-missing"),
      invalid: node.getAttribute("data-invalid"),
    };
  }

  themeEmptyVisible() {
    const node = this.list("external-theme-empty");
    if (!node) return null;
    return !node.classList.contains("hidden");
  }

  // Every set_configs payload, in the order the GUI made the calls.
  savePayloads() {
    return this.callsOf("set_configs").map(function (entry) { return entry.args[0]; });
  }

  logErrorCount() {
    const area = this.list("log-area");
    if (!area) return -1;
    let count = 0;
    for (let i = 0; i < area.children.length; i += 1) {
      if (area.children[i].classList.contains("log-err")) count += 1;
    }
    return count;
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

  // ── settings surface probes (DOM only, like every probe above) ────────────
  settingsVisible() {
    const node = this.list("settings-page");
    if (!node) return null;
    return !node.classList.contains("hidden");
  }

  // Installed themes as the settings page renders them. `valid` is a fact about the
  // installation and is deliberately separate from the carry set's row states.
  inventoryRows() {
    const list = this.list("settings-theme-list");
    if (!list) return null;
    const rows = [];
    for (let i = 0; i < list.children.length; i += 1) {
      const row = list.children[i];
      const id = row.getAttribute ? row.getAttribute("data-theme-id") : null;
      if (!id) continue;
      const reason = row.querySelector("[data-theme-reason]");
      const remove = row.querySelector('[data-theme-action="remove"]');
      rows.push({
        id: id,
        valid: row.getAttribute("data-theme-valid") === "true",
        reason: reason ? reason.textContent.trim() : null,
        removeDisabled: remove ? remove.disabled : null,
      });
    }
    return rows;
  }

  inventoryRow(id) {
    const rows = this.inventoryRows() || [];
    for (let i = 0; i < rows.length; i += 1) {
      if (rows[i].id === id) return rows[i];
    }
    return null;
  }

  inventoryIds() {
    return (this.inventoryRows() || []).map(function (row) { return row.id; }).sort();
  }

  // Facts are read from the rendered value, never from a JS constant: a page that
  // hard-codes a path would render nothing here.
  facts(rootId) {
    const root = this.list(rootId);
    if (!root) return null;
    const out = {};
    for (let i = 0; i < root.children.length; i += 1) {
      const row = root.children[i];
      const key = row.getAttribute ? row.getAttribute("data-fact") : null;
      if (!key) continue;
      const value = row.querySelector("[data-fact-value]");
      out[key] = value ? value.textContent.trim() : null;
    }
    return out;
  }

  close() { this.window.close(); }
}

export async function bootGui(options) {
  const settings = options || {};
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
  const methods = ["get_templates", "get_config", "set_configs", "get_theme_state",
    "prepare_conversion", "convert",
    "select_input_files", "select_input_directory", "select_output_directory",
    "open_file", "open_directory",
    // Phase 9B1: the settings surface has its own calls. The three readers are asked
    // for lazily when the page opens, so giving them a default reply cannot change any
    // existing contract's startup path; the four management actions stay pending and
    // are resolved (or rejected) by the contract that drives them.
    "get_theme_inventory", "import_theme", "remove_theme", "export_theme_template",
    "open_theme_location", "get_storage_info", "get_about_info"];
  methods.forEach(function (name) {
    calls[name] = [];
    api[name] = function () {
      const args = Array.prototype.slice.call(arguments);
      const entry = { args: args, settled: false, deferred: deferred() };
      calls[name].push(entry);
      if (AUTO_RESOLVE[name]) {
        entry.settled = true;
        entry.deferred.resolve(AUTO_RESOLVE[name]());
        return entry.deferred.promise;
      }
      // The theme state is a normal bridge reply: auto-resolved to the state the
      // contract asked for, or left open for a contract that needs to answer it (or
      // fail it) itself.
      if (name === "get_theme_state" && settings.autoThemeState !== false) {
        entry.settled = true;
        const state = settings.themeState || EMPTY_THEME_STATE;
        entry.deferred.resolve(JSON.parse(JSON.stringify(state)));
      }
      // The settings facts behave the same way: default replies unless a contract
      // answers them itself (autoSettings: false).
      if (name === "get_theme_inventory" && settings.autoSettings !== false) {
        entry.settled = true;
        const inventory = settings.themeInventory || EMPTY_THEME_INVENTORY;
        entry.deferred.resolve(JSON.parse(JSON.stringify(inventory)));
      }
      if (name === "get_storage_info" && settings.autoSettings !== false) {
        entry.settled = true;
        const storage = settings.storageInfo || STORAGE_INFO_SAMPLE;
        entry.deferred.resolve(JSON.parse(JSON.stringify(storage)));
      }
      if (name === "get_about_info" && settings.autoSettings !== false) {
        entry.settled = true;
        const about = settings.aboutInfo || ABOUT_INFO_SAMPLE;
        entry.deferred.resolve(JSON.parse(JSON.stringify(about)));
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
  const session = new GuiSession(dom, window, calls, errors, settings);
  await session.ready();
  return session;
}
