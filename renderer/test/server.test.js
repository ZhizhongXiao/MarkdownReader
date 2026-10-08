"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const ARTIFACT = path.resolve(__dirname, "..", "dist", "renderer.cjs");

function run(lines) {
  return spawnSync(process.execPath, [ARTIFACT, "--server"], {
    input: lines.join("\n"),
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
    timeout: 15000,
  });
}

test("server preserves request order and IDs through invalid frames and stdin EOF", () => {
  const result = run([
    "not json",
    JSON.stringify({ protocol: 9, id: "version", request: { markdown: "x" } }),
    JSON.stringify({ protocol: 1, request: { markdown: "x" } }),
    JSON.stringify({ protocol: 1, id: "shape", request: { markdown: 42 } }),
    JSON.stringify({ protocol: 1, id: "中文 5", request: { markdown: "# after\n\nEOF" } }),
  ]);
  assert.equal(result.status, 0, result.stderr);
  const frames = result.stdout.trim().split("\n").map(JSON.parse);
  assert.equal(frames.length, 5);
  assert.deepEqual(frames.map((frame) => frame.id), [null, "version", null, "shape", "中文 5"]);
  assert.ok(frames.every((frame) => frame.protocol === 1));
  assert.deepEqual(frames.slice(0, 4).map((frame) => frame.response.error.code), [
    "invalid_json", "invalid_protocol", "invalid_request", "invalid_request",
  ]);
  assert.equal(frames[4].response.ok, true);
  assert.match(frames[4].response.html, /after<\/h1>/);
  assert.match(result.stderr, /invalid_json/);
});

test("server keeps first-use smoke separate from document options and later responses", () => {
  const result = run([
    JSON.stringify({
      protocol: 1, id: "smoke", request: {
        markdown: "$a^2$", options: { math: false, fetch_remote_resources: false },
        runtime_validation: {
          markdown: "$b^2$", options: { math: true, fetch_remote_resources: false },
        },
      },
    }),
    JSON.stringify({ protocol: 1, id: "plain", request: { markdown: "plain" } }),
  ]);
  assert.equal(result.status, 0, result.stderr);
  const [first, second] = result.stdout.trim().split("\n").map(JSON.parse);
  assert.match(first.response.runtime_validation.html, /class="katex"/);
  assert.equal(first.response.runtime_validation.warnings.length, 0);
  assert.equal(first.response.features.katex, false);
  assert.equal(first.response.resources.styles.length, 0);
  assert.equal(first.response.warnings.length, 1);
  assert.equal(Object.hasOwn(second.response, "runtime_validation"), false);
  assert.deepEqual(second.response.warnings, []);
  assert.deepEqual(second.response.resources.styles, []);
});
