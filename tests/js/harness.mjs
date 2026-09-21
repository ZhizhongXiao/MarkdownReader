// Stage 6.1a — shared jsdom harness for templates/viewer.js behaviour contracts.
//
// Test-only. Not shipped: packaging/MarkdownReader.spec collects only
// gui/assets, templates and node_renderer, so tests/js never reaches the EXE.
//
// Two rules this harness exists to enforce, both learned from the Stage 5
// false-guardrail incident ("href=\"file:" that could never fail):
//   1. A contract must not be able to pass on a page where init() never ran.
//      jsdom parses the fixture with readyState "loading", so viewer.js would
//      take its DOMContentLoaded branch and silently never initialise. boot()
//      therefore waits for the document to settle BEFORE evaluating viewer.js,
//      and every session exposes liveness sentinels that contracts assert on.
//   2. jsdom has no layout engine: scroll clamping is unobservable. Scroll
//      contracts are written against observable ordering and calls instead.
//
// localStorage in jsdom is per-instance, so a second boot() only reproduces a
// "reload" when the previous session's storage snapshot is passed back in.

import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

export const HIDDEN_CLASS = "is-hidden-by-content-fold";
export const TOC_HIDDEN_CLASS = "is-hidden-by-collapse";
export const LEGACY_FOLD_KEY = "markdownreader-expandlevel";
export const LEGACY_TOC_KEY = "markdownreader-toc-collapsed-v2";
export const DOC_STATE_PREFIX = "markdownreader-doc-state-v2:";

function env(name) {
  const value = process.env[name];
  if (!value) throw new Error("harness: missing environment variable " + name);
  return value;
}

const VIEWER_SOURCE = readFileSync(env("MR_VIEWER_JS"), "utf8").replace(/^\uFEFF/, "");

const FIXTURES = {
  A: () => ({ html: readFileSync(env("MR_FIXTURE_A"), "utf8"), url: env("MR_FIXTURE_A_URL") }),
  B: () => ({ html: readFileSync(env("MR_FIXTURE_B"), "utf8"), url: env("MR_FIXTURE_B_URL") }),
};

class FakeIntersectionObserver {
  constructor(callback, options) {
    this.callback = callback;
    this.options = options;
    this.targets = [];
    FakeIntersectionObserver.instances.push(this);
  }
  observe(element) { this.targets.push(element); }
  unobserve(element) { this.targets = this.targets.filter((item) => item !== element); }
  disconnect() { this.targets = []; }
  trigger(target, isIntersecting) {
    this.callback(
      [{ target, isIntersecting, intersectionRatio: isIntersecting ? 1 : 0, time: 0 }],
      this,
    );
  }
}
FakeIntersectionObserver.instances = [];

export function storageSnapshot(window) {
  const store = window.localStorage;
  const out = {};
  for (let index = 0; index < store.length; index += 1) {
    const key = store.key(index);
    out[key] = store.getItem(key);
  }
  return out;
}

export function docStateOf(storage, pathname) {
  const raw = storage[DOC_STATE_PREFIX + pathname];
  if (!raw) return null;
  try { return JSON.parse(raw); } catch (error) { return null; }
}

function documentSettled(dom) {
  return new Promise((resolve) => {
    if (dom.window.document.readyState === "complete") { resolve(); return; }
    dom.window.addEventListener("load", () => resolve(), { once: true });
  });
}

export class ViewerSession {
  constructor({ dom, window, spy, errors, scrollLog }) {
    this.dom = dom;
    this.window = window;
    this.spy = spy;
    this.errors = errors;
    this.scrollLog = scrollLog;
    this.doc = window.document;
    this.area = this.doc.getElementById("content-area");
    this.body = this.doc.getElementById("markdown-body");
  }

  // ── liveness sentinels: a contract must prove the page really initialised ──
  sentinels() {
    return {
      readyState: this.doc.readyState,
      errors: this.errors.slice(),
      contentArea: !!this.area,
      markdownBody: !!this.body,
      headingToggles: this.doc.querySelectorAll(".heading-toggle").length,
      tableWrappers: this.doc.querySelectorAll(".table-wrapper").length,
      tocToggles: this.doc.querySelectorAll(".toc-toggle").length,
      observed: FakeIntersectionObserver.instances.reduce(
        (total, instance) => total + instance.targets.length, 0),
      headings: this.headings().length,
      tocRows: this.tocRows().length,
    };
  }

  // ── content model ─────────────────────────────────────────────────────────
  headings() {
    return Array.from(
      this.body.querySelectorAll("h1[id], h2[id], h3[id], h4[id], h5[id], h6[id]"),
    );
  }

  headingText(heading) {
    return Array.from(heading.childNodes).map((node) => {
      if (node.nodeType === 3) return node.textContent || "";
      if (node.nodeType === 1 && !node.classList.contains("heading-toggle")) {
        return node.textContent || "";
      }
      return "";
    }).join("").trim();
  }

  headingStartingWith(prefix) {
    const found = this.headings().filter((h) => this.headingText(h).startsWith(prefix));
    if (found.length !== 1) {
      throw new Error(
        "harness: expected exactly one heading starting with " + JSON.stringify(prefix) +
        " but found " + found.length + " in " +
        JSON.stringify(this.headings().map((h) => this.headingText(h))),
      );
    }
    return found[0];
  }

  isHidden(element) { return element.classList.contains(HIDDEN_CLASS); }

  hidden() { return Array.from(this.body.querySelectorAll("." + HIDDEN_CLASS)); }

  hiddenCount() { return this.body.querySelectorAll("." + HIDDEN_CLASS).length; }

  numbered() {
    return this.headings()
      .filter((h) => h.classList.contains("no-autonumber"))
      .map((h) => this.headingText(h));
  }

  // ── TOC model ─────────────────────────────────────────────────────────────
  tocRows() { return Array.from(this.doc.querySelectorAll(".toc-row")); }

  tocRow(id) { return this.doc.querySelector('.toc-row[data-id="' + id + '"]'); }

  tocCollapsedIds() {
    return this.tocRows().filter((row) => row.classList.contains("is-collapsed"))
      .map((row) => row.getAttribute("data-id"));
  }

  tocHiddenIds() {
    return this.tocRows().filter((row) => row.classList.contains(TOC_HIDDEN_CLASS))
      .map((row) => row.getAttribute("data-id"));
  }

  // ── interaction ───────────────────────────────────────────────────────────
  click(element) {
    if (!element) throw new Error("harness: cannot click a missing element");
    element.dispatchEvent(new this.window.MouseEvent("click", { bubbles: true, cancelable: true }));
  }

  clickHeadingToggle(heading) { this.click(heading.querySelector(".heading-toggle")); }

  clickToolbar(buttonId) { this.click(this.doc.getElementById(buttonId)); }

  clickTocToggle(id) { this.click(this.tocRow(id).querySelector(".toc-toggle")); }

  clickTocLink(id) { this.click(this.tocRow(id).querySelector(".toc-link")); }

  scrollTo(value) {
    this.area.scrollTop = value;
    this.area.dispatchEvent(new this.window.Event("scroll"));
  }

  // ── observation helpers ───────────────────────────────────────────────────
  storage() { return storageSnapshot(this.window); }

  sleep(ms) { return new Promise((resolve) => this.window.setTimeout(resolve, ms)); }

  frames(count) {
    return new Promise((resolve) => {
      let left = count;
      const step = () => {
        if (left <= 0) { resolve(); return; }
        left -= 1;
        this.window.requestAnimationFrame(step);
      };
      step();
    });
  }

  fireSpy(id, isIntersecting = true) {
    const target = this.doc.getElementById(id);
    if (!target) throw new Error("harness: no body heading with id " + id);
    let fired = 0;
    FakeIntersectionObserver.instances.forEach((instance) => {
      if (instance.targets.indexOf(target) === -1) return;
      instance.trigger(target, isIntersecting);
      fired += 1;
    });
    return fired;
  }

  // jsdom has no layout engine, so the visible symptom of a clear-then-rebuild
  // pass (a flicker) cannot be observed. This records the class-list operations
  // on the hidden class instead: a one-pass reconcile never removes it from an
  // element that stays hidden, so any removal during a collapse is the
  // artifact. This is deliberately the only contract that observes mechanism
  // rather than state, because the user-visible form is unobservable here.
  async hiddenClassOperations(action) {
    const proto = this.window.DOMTokenList.prototype;
    const original = { add: proto.add, remove: proto.remove, toggle: proto.toggle };
    const counts = { adds: 0, removes: 0 };
    proto.add = function (token) {
      if (token === HIDDEN_CLASS) counts.adds += 1;
      return original.add.apply(this, arguments);
    };
    proto.remove = function (token) {
      if (token === HIDDEN_CLASS) counts.removes += 1;
      return original.remove.apply(this, arguments);
    };
    proto.toggle = function (token, force) {
      if (token === HIDDEN_CLASS) {
        const has = original.contains.call(this, token);
        const next = force === undefined ? !has : !!force;
        if (next) counts.adds += 1;
        else counts.removes += 1;
      }
      return original.toggle.apply(this, arguments);
    };
    try {
      action();
      await this.sleep(0);
    } finally {
      proto.add = original.add;
      proto.remove = original.remove;
      proto.toggle = original.toggle;
    }
    return counts;
  }

  close() { this.window.close(); }
}

export async function boot({ variant = "A", seed = {} } = {}) {
  const { html, url } = FIXTURES[variant]();
  const dom = new JSDOM(html, { url, pretendToBeVisual: true, runScripts: "outside-only" });
  const { window } = dom;
  const errors = [];
  window.console.error = (...args) => errors.push(args.map(String).join(" "));

  const spy = { scrollIntoView: [] };
  FakeIntersectionObserver.instances = [];
  window.IntersectionObserver = FakeIntersectionObserver;
  window.Element.prototype.scrollIntoView = function scrollIntoView(options) {
    spy.scrollIntoView.push({ id: this.id || "", options: options || null });
  };
  Object.entries(seed).forEach(([key, value]) => window.localStorage.setItem(key, value));

  await documentSettled(dom);

  const session = new ViewerSession({ dom, window, spy, errors, scrollLog: [] });
  Object.defineProperty(session.area, "scrollTop", {
    configurable: true,
    get() { return this.__scrollTop || 0; },
    set(value) {
      this.__scrollTop = value;
      session.scrollLog.push({
        value,
        hiddenAtWrite: session.hiddenCount(),
        pathname: window.location.pathname,
      });
    },
  });

  window.eval(VIEWER_SOURCE);
  return session;
}
