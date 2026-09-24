"use strict";

/**
 * renderer 冒烟测试（node:test）：只验证构建产物能否按协议工作。
 * 契约级检查在 Python 侧（tests/test_renderer_adapter_*.py）。
 *
 * Phase 5A：协议为 v2，成功 envelope 始终带 resources（没有资源时也是空结构）；
 * v1 的 assets.css 只属于旧 production renderer，不再是 adapter 契约。
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

// v2 的 resources.styles 携带内嵌字体的 KaTeX 样式（约 1.4 MB），超过 spawnSync 默认 1 MiB buffer。
const MAX_BUFFER = 32 * 1024 * 1024;

function run(input) {
  return spawnSync(process.execPath, [ARTIFACT], {
    input: typeof input === "string" ? input : JSON.stringify(input),
    encoding: "utf8",
    maxBuffer: MAX_BUFFER,
  });
}

function describe(result) {
  return (result.error ? "spawn error: " + result.error.message + "\n" : "") + result.stderr;
}

test("build artifact exists (run npm run build first)", function () {
  assert.ok(fs.existsSync(ARTIFACT), "缺少构建产物：请运行 npm run build");
});

test("stdout is one JSON v2 envelope with features, headings and resources", function () {
  const result = run(REQUEST);
  assert.strictEqual(result.status, 0, describe(result));
  const envelope = JSON.parse(result.stdout);
  assert.strictEqual(envelope.protocol_version, 2);
  assert.strictEqual(envelope.ok, true);
  assert.ok(envelope.html.includes('class="katex"'), envelope.html);
  assert.strictEqual(envelope.features.katex, true);
  assert.strictEqual(envelope.features.wikilink, true);
  assert.strictEqual(envelope.features.obsidian_tag, true);
  assert.strictEqual(envelope.features.plantuml, false);
  assert.ok(envelope.headings[0].anchor.length > 0, JSON.stringify(envelope.headings));
  assert.ok(Array.isArray(envelope.warnings));
  assert.ok(!Object.prototype.hasOwnProperty.call(envelope, "assets"), "v1 的 assets.css 不属于 v2");
  assert.strictEqual(envelope.resources.styles.length, 1, JSON.stringify(Object.keys(envelope)));
  assert.strictEqual(envelope.resources.styles[0].id, "katex");
  assert.ok(envelope.resources.styles[0].css.includes("data:font/woff2;base64,"));
  assert.deepStrictEqual(envelope.resources.scripts, [], "没有 Mermaid 就不带 runtime");
});

test("resources is present and empty when the document has none", function () {
  const result = run({ markdown: "只有普通文本。\n" });
  assert.strictEqual(result.status, 0, describe(result));
  const envelope = JSON.parse(result.stdout);
  assert.deepStrictEqual(envelope.resources, { items: [], styles: [], scripts: [] });
  assert.deepStrictEqual(envelope.warnings, []);
});

test("the mermaid runtime is delivered only for mermaid documents", function () {
  const withMermaid = JSON.parse(run({ markdown: "```mermaid\ngraph LR\nA --> B\n```\n" }).stdout);

  assert.strictEqual(withMermaid.resources.scripts.length, 1);
  assert.strictEqual(withMermaid.resources.scripts[0].id, "mermaid");
  assert.strictEqual(withMermaid.resources.scripts[0].version, "11.15.0");
  assert.ok(withMermaid.resources.scripts[0].script.includes('globalThis["mermaid"]'));
  assert.ok(withMermaid.resources.scripts[0].boot.includes("mermaid.run"));
  assert.ok(!withMermaid.html.includes("<script"), "adapter 不自己注入脚本：注入属 assembler");

  const without = JSON.parse(run({ markdown: "只有普通文本。\n" }).stdout);
  assert.deepStrictEqual(without.resources.scripts, []);
});

test("malformed input fails with an error envelope on stdout and diagnostics on stderr", function () {
  const result = run("not json");
  assert.notStrictEqual(result.status, 0);
  const envelope = JSON.parse(result.stdout);
  assert.strictEqual(envelope.ok, false);
  assert.strictEqual(envelope.error.code, "invalid_json");
  assert.strictEqual(envelope.protocol_version, 2);
  assert.ok(result.stderr.length > 0);
});