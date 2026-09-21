// Stage 6.7a - jsdom harness for the real generated index page (the output of
// core/index_builder.build_index, i.e. templates/index/index.html with
// templates/index/index.js inlined). Test-only; no production code here.
//
// Two things this harness does differently from the viewer harness, on purpose:
//
//   * Errors are read through a jsdom VirtualConsole. jsdom reports an exception
//     thrown inside a DOM listener as a "jsdomError", and it does NOT route that
//     through window.console.error, so an override of window.console.error is
//     blind to exactly the failures contract IX2 is about.
//   * document.execCommand is stubbed. jsdom ships none at all (its type is
//     "undefined"), so the real fallback path would die with a TypeError instead
//     of returning false - and returning false is the case I1 is about.
//
// The page is instantiated with runScripts: "outside-only" so the script inlined
// in the generated page does not run by itself: a contract can reshape the DOM or
// the clipboard stub first, and then evaluate the real template script.

import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error("index harness: missing environment variable " + name);
  return value;
}

const INDEX_HTML = readFileSync(requiredEnv("MR_INDEX_HTML"), "utf8");
const INDEX_URL = requiredEnv("MR_INDEX_URL");

// Both are exported so a contract can prove the generated page really inlines the
// script this harness evaluates, instead of two files silently drifting apart.
export const INDEX_PAGE = INDEX_HTML;
export const INDEX_SOURCE = readFileSync(requiredEnv("MR_INDEX_JS"), "utf8").replace(/^\uFEFF/, "");

// Line endings are normalised before any text comparison on purpose: the
// builder writes its output in text mode, so on Windows the inlined script
// carries CRLF while the template file on disk carries LF. That is how the
// page is produced, not drift - but a changed script still fails here.
function normalizedText(text) {
  return String(text)
    .replace(/^\uFEFF/, "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");
}

function settled(window) {
  return new Promise(function (resolve) {
    window.setTimeout(resolve, 0);
  });
}

export class IndexSession {
  constructor(dom, window, journal) {
    this.dom = dom;
    this.window = window;
    this.doc = window.document;
    this.journal = journal;
  }

  // ── stub accounting ──────────────────────────────────────────────
  clipboardCalls() { return this.journal.clipboard.slice(); }

  execCalls() { return this.journal.exec.slice(); }

  // The text the fallback really staged, read from the textarea it appends, so
  // the contract never has to look inside the page script.
  execTexts() { return this.journal.execText.slice(); }

  // ── outcome probes ───────────────────────────────────────────────
  initError() { return this.journal.initError; }

  errors() { return this.journal.errors.slice(); }

  async settle(ticks) {
    const count = ticks || 3;
    for (let i = 0; i < count; i += 1) {
      await settled(this.window);
    }
  }

  // ── DOM probes (state via the DOM, never via the page internals) ──
  element(selector) { return this.doc.querySelector(selector); }

  all(selector) { return Array.from(this.doc.querySelectorAll(selector)); }

  group(folder) {
    return this.doc.querySelector('.folder-group[data-folder="' + folder + '"]');
  }

  isHidden(node) {
    if (!node) throw new Error("index harness: asked whether a missing node is hidden");
    return Boolean(node.hidden) || node.hasAttribute("hidden");
  }

  visibleRows(scope) {
    return this.all(".document-row").filter(function (row) {
      return scope ? scope.contains(row) && !row.hidden : !row.hidden;
    });
  }

  toggleOf(group) { return group.querySelector(".toggle-btn"); }

  listOf(group) { return group.querySelector(":scope > .document-list"); }

  copyButtonOf(group) { return group.querySelector(".copy-btn"); }

  click(node) {
    if (!node) throw new Error("index harness: no such element to click");
    node.click();
  }

  type(node, text) {
    if (!node) throw new Error("index harness: no such input to type into");
    node.value = text;
    node.dispatchEvent(new this.window.Event("input", { bubbles: true }));
  }

  copyFeedback(button) {
    return {
      text: button.textContent,
      copied: button.classList.contains("copied"),
      title: button.title,
    };
  }

  // The one thing I1 is about: whether the button claims the copy happened.
  // Deliberately neutral about any failure UX - it only rejects a success claim.
  claimsSuccess(button) {
    const state = this.copyFeedback(button);
    return state.text === "✓" || state.copied || state.title === "已复制";
  }

  // The folder path the page is expected to copy, derived the way the page
  // derives it (from the index page's own URL), so the assertion compares against
  // a real expectation instead of a hardcoded path.
  indexDirectory() {
    const raw = decodeURIComponent(this.window.location.pathname);
    const path = (raw.charAt(0) === "/" ? raw.slice(1) : raw).split("/").join("\\");
    return path.slice(0, path.lastIndexOf("\\"));
  }

  folderPath(folder) {
    const base = this.indexDirectory();
    return folder ? base + "\\" + folder : base;
  }

  inlinesSource() {
    return normalizedText(INDEX_PAGE).indexOf(normalizedText(INDEX_SOURCE)) !== -1;
  }

  // Errors as one readable line, for assertion messages.
  errorSummary() {
    const parts = [];
    if (this.journal.initError) parts.push("init threw " + this.journal.initError.message);
    this.journal.errors.forEach(function (entry) { parts.push(entry); });
    return parts.length ? "[" + parts.join(" | ") + "]" : "[]";
  }

  close() { this.window.close(); }
}

export async function boot(options) {
  const settings = options || {};
  const journal = {
    errors: [],
    initError: null,
    clipboard: [],
    exec: [],
    execText: [],
    execReturns: false,
  };
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", function (error) {
    journal.errors.push(String((error && error.message) || error));
  });

  const dom = new JSDOM(INDEX_HTML, {
    url: INDEX_URL,
    runScripts: "outside-only",
    virtualConsole: virtualConsole,
    pretendToBeVisual: true,
  });
  const window = dom.window;

  // jsdom has no clipboard, so the page would take the fallback path for the
  // wrong reason. A contract says which outcome it wants instead.
  if (settings.clipboard) {
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: function (text) {
          journal.clipboard.push(text);
          return settings.clipboard === "resolve"
            ? Promise.resolve()
            : Promise.reject(new Error("clipboard denied"));
        },
      },
    });
  }

  // jsdom ships no execCommand; what it returns is the whole question in IX1-C.
  journal.execReturns = settings.execCommand === true;
  window.document.execCommand = function (command) {
    journal.exec.push(command);
    const staged = window.document.querySelector("textarea");
    journal.execText.push(staged ? staged.value : null);
    return journal.execReturns;
  };

  // Reshaping the DOM has to happen before the page script runs, which is what
  // runScripts: "outside-only" buys.
  if (typeof settings.mutate === "function") settings.mutate(window.document);

  await settled(window);

  try {
    window.eval(INDEX_SOURCE);
  } catch (error) {
    journal.initError = error;
  }

  return new IndexSession(dom, window, journal);
}
