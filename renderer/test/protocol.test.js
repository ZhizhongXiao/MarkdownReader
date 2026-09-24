"use strict";

/**
 * renderer 冒烟测试（node:test）：只验证构建产物能否按协议工作。
 * 契约级检查在 Python 侧（tests/test_renderer_adapter_*.py）。
 */

const assert = require("node:assert");
const { test } = require("node:test");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ARTIFACT = path.resolve(__dirname, "..", "dist", "renderer.cjs");
const REQUEST = {
  markdown: "# 标题\n\n正文 $a^2+b^2=c^2$、[[目标]] 与 #note。\n",
  options: {},
  context: { source_path: "", output_path: "", document_map: {} },
};

function run(input) {
  return spawnSync(process.execPath, [ARTIFACT], {
    input: typeof input === "string" ? input : JSON.stringify(input),
    encoding: "utf8",
  });
}

test("build artifact exists (run npm run build first)", function () {
  assert.ok(fs.existsSync(ARTIFACT), "缺少构建产物：请运行 npm run build");
});

test("stdout is one JSON envelope with protocol_version, features and headings", function () {
  const result = run(REQUEST);
  assert.strictEqual(result.status, 0, result.stderr);
  const envelope = JSON.parse(result.stdout);
  assert.strictEqual(envelope.protocol_version, 1);
  assert.strictEqual(envelope.ok, true);
  assert.ok(envelope.html.includes('class="katex"'), envelope.html);
  assert.strictEqual(envelope.features.katex, true);
  assert.strictEqual(envelope.features.wikilink, true);
  assert.strictEqual(envelope.features.obsidian_tag, true);
  assert.strictEqual(envelope.features.plantuml, false);
  assert.ok(envelope.headings[0].anchor.length > 0, JSON.stringify(envelope.headings));
  assert.ok(Array.isArray(envelope.warnings));
});

test("malformed input fails with an error envelope on stdout and diagnostics on stderr", function () {
  const result = run("not json");
  assert.notStrictEqual(result.status, 0);
  const envelope = JSON.parse(result.stdout);
  assert.strictEqual(envelope.ok, false);
  assert.strictEqual(envelope.error.code, "invalid_json");
  assert.ok(result.stderr.length > 0);
});
