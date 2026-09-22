// Stage 7.1 - harness self-checks. Test infrastructure, not the viewer page.
//
// These checks exist because the viewer harness read page errors from one channel
// only: an override of window.console.error. jsdom reports an exception thrown
// inside a DOM listener on its virtual console instead, and no virtual console
// was installed, so those exceptions were invisible to every viewer contract.
//
//   SC1  the historical gap, asserted as a fact: console.error alone sees nothing
//   SC2  the harness itself must surface a listener exception  <- this was red
//   SC3  the console.error channel must not regress
//   SC4  jsdom capability notices are separated by type, never counted as errors
//   SC5  a clean page reports nothing at all
//
// The suite builds its own minimal pages, so it never depends on a fixture and
// never says anything about templates/viewer.js.

import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

import { viewerErrorVirtualConsole, attachPageErrorChannel } from "./harness.mjs";

// Reporting contract: one synchronous line per check, emitted while that check is
// still running. The Python caller counts these lines, and the prefix is
// deliberately not "CONTRACT" so this module can never change the viewer record
// count.
function check(name, body) {
  test(name, async () => {
    let failure = null;
    try {
      await body();
    } catch (error) {
      failure = error;
    }
    console.log("SELFCHECK " + (failure ? "fail" : "pass") + " " + name);
    if (failure) throw failure;
  });
}

function settle(window) {
  return new Promise(function (resolve) {
    window.setTimeout(resolve, 0);
  });
}

// A page driven through the harness pieces under test, so the checks exercise the
// real mechanism rather than a copy of it.
function probePage() {
  const journal = { errors: [], notices: [] };
  const virtualConsole = viewerErrorVirtualConsole(journal);
  const dom = new JSDOM("", {
    url: "http://localhost/C:/probe/index.html",
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: virtualConsole,
  });
  const window = dom.window;
  attachPageErrorChannel(window, journal);
  return { dom: dom, window: window, journal: journal };
}

function clickThrowingListener(window) {
  window.eval(
    "document.body.addEventListener(\"click\", function () {" +
    " var missing = null; missing.hidden = true; });",
  );
  window.document.body.click();
}

check("SC1 console.error alone sees no listener exception", async () => {
  const probe = probePage();
  try {
    // The pre-fix harness: the override and nothing else.
    const onlyConsole = [];
    probe.window.console.error = function () {
      onlyConsole.push(Array.prototype.map.call(arguments, String).join(" "));
    };
    clickThrowingListener(probe.window);
    await settle(probe.window);
    assert.deepEqual(onlyConsole, [],
      "nothing reaches the override, which is the gap that made a second channel necessary");
  } finally {
    probe.dom.window.close();
  }
});

check("SC2 the harness surfaces a listener exception", async () => {
  const probe = probePage();
  try {
    clickThrowingListener(probe.window);
    await settle(probe.window);
    assert.equal(probe.journal.errors.length, 1,
      "an exception thrown inside a listener must reach the harness, got "
      + JSON.stringify(probe.journal.errors));
    // Asserted on the language rather than on jsdom wording: the listener throws a
    // TypeError by construction, and it must be classified as an error instead of
    // being parked among the notices.
    assert.ok(probe.journal.errors[0].indexOf("TypeError") !== -1,
      "and it must be the listener failure: " + JSON.stringify(probe.journal.errors));
    assert.deepEqual(probe.journal.notices, [],
      "an uncaught exception must not be filed as a notice");
  } finally {
    probe.dom.window.close();
  }
});

check("SC3 a page writing to console.error is still surfaced", async () => {
  const probe = probePage();
  try {
    probe.window.console.error("a page-written note");
    assert.deepEqual(probe.journal.errors, ["a page-written note"],
      "the original channel must not regress");
  } finally {
    probe.dom.window.close();
  }
});

check("SC4 a jsdom notice is separated by type, not counted as an error", async () => {
  const probe = probePage();
  try {
    probe.window.alert("x");
    await settle(probe.window);
    assert.deepEqual(probe.journal.errors, [],
      "a jsdom capability notice is not a page error");
    assert.equal(probe.journal.notices.length, 1,
      "the notice must still be recorded: " + JSON.stringify(probe.journal.notices));
    assert.equal(probe.journal.notices[0].type, "not-implemented",
      "and it must keep its structured type");
  } finally {
    probe.dom.window.close();
  }
});

check("SC5 a clean page reports nothing", async () => {
  const probe = probePage();
  try {
    probe.window.eval(
      "document.body.addEventListener(\"click\", function () {" +
      " document.body.setAttribute(\"data-clicked\", \"1\"); });",
    );
    probe.window.document.body.click();
    await settle(probe.window);
    assert.deepEqual(probe.journal.errors, [], "a listener that does not throw reports nothing");
    assert.deepEqual(probe.journal.notices, [], "and produces no notice");
  } finally {
    probe.dom.window.close();
  }
});
