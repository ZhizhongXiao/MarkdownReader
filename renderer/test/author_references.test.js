"use strict";

/**
 * Cutover C1：作者 raw HTML provenance 通道（node 侧）。
 *
 * 与 `tests/test_renderer_author_references.py` 共用 `tests/fixtures/author_references.json`：
 *   - `raw_fragments`：直接喂给 `referencesInRawHtml` / `collectAuthorReferences`（scanner 规则层）
 *   - `documents`：spawn 真实 dist，断言 envelope 的 `resources.author_references`（token 层 + 接线）
 *
 * 于是「raw HTML 与 Markdown 生成的 HTML 可区分」和「两侧规则同构」由同一批 fixture 同时钉住。
 */

const assert = require("node:assert");
const { test } = require("node:test");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const {
  collectAuthorReferences,
  referencesInRawHtml,
} = require("../document/author_references");

const ARTIFACT = path.join(__dirname, "..", "dist", "renderer.cjs");
const FIXTURE_PATH = path.join(
  __dirname,
  "..",
  "..",
  "tests",
  "fixtures",
  "author_references.json",
);
const FIXTURES = JSON.parse(fs.readFileSync(FIXTURE_PATH, "utf8"));

function tokensFromRaw(raw) {
  return [{ type: "html_block", content: raw + "\n" }];
}

function renderEnvelope(markdown) {
  assert.ok(
    fs.existsSync(ARTIFACT),
    "缺少 renderer/dist/renderer.cjs：先执行 cd renderer; npm ci; npm run build",
  );
  const completed = spawnSync(process.execPath, [ARTIFACT], {
    input: JSON.stringify({ markdown: markdown, options: {}, context: {} }),
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  assert.strictEqual(completed.status, 0, completed.stderr);
  return JSON.parse(completed.stdout);
}

for (const fixture of FIXTURES.raw_fragments) {
  test("raw fragment: " + fixture.name, function () {
    const collected = collectAuthorReferences(tokensFromRaw(fixture.raw));

    assert.deepStrictEqual(
      collected,
      fixture.expected,
      "scanner refs: " + JSON.stringify(referencesInRawHtml(fixture.raw)),
    );
  });
}

for (const fixture of FIXTURES.documents) {
  test("document: " + fixture.name, function () {
    const envelope = renderEnvelope(fixture.markdown);

    assert.deepStrictEqual(envelope.resources.author_references, fixture.expected);
  });
}

test("every envelope carries the author_references channel", function () {
  const envelope = renderEnvelope("只有普通文本。\n");

  assert.deepStrictEqual(envelope.resources.author_references, []);
  assert.strictEqual(envelope.protocol_version, 2, "additive 通道不升协议版本");
});

test("navigation anchors and script text never enter the channel", function () {
  const envelope = renderEnvelope('<a href="https://nav.invalid/p">链接</a>\n');

  assert.deepStrictEqual(envelope.resources.author_references, []);
});
