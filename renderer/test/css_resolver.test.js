"use strict";

/**
 * 通用 CSS 资源 resolver 的单元测试（Phase 5A，node:test）。
 *
 * 它不感知 Theme：输入一段 CSS 与 base directory，输出内联后的 CSS 与 manifest items。
 * 本阶段只把它接到 KaTeX 样式；Phase 6/7 的 theme CSS 复用同一模块。
 */

const assert = require("node:assert");
const { test } = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { extractCssReferences, resolveCssResources } = require("../resources/css_resolver");
const { createLocalFileReader } = require("../resources/local_file");

const FONT_BYTES = Buffer.from("woff2-fixture");
const FONT_REFERENCE = "fonts/Demo-Regular.woff2";

function tempDirectory() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "mr-css-resolver-"));
}

function writeFont(directory) {
  const font = path.join(directory, "fonts", "Demo-Regular.woff2");
  fs.mkdirSync(path.dirname(font), { recursive: true });
  fs.writeFileSync(font, FONT_BYTES);
  return font;
}

function resolve(css, baseDirectory) {
  const warnings = [];
  const result = resolveCssResources(css, baseDirectory, createLocalFileReader(), warnings);
  return { css: result.css, items: result.items, warnings: warnings };
}

test("a readable url() becomes a base64 data URI and is reported in the manifest", function () {
  const directory = tempDirectory();
  const font = writeFont(directory);

  const result = resolve('@font-face{font-family:Demo;src:url("' + FONT_REFERENCE + '")}', directory);

  assert.strictEqual(
    result.css,
    "@font-face{font-family:Demo;src:url(data:font/woff2;base64," +
      FONT_BYTES.toString("base64") +
      ")}",
  );
  assert.deepStrictEqual(result.items, [
    {
      kind: "css-resource",
      source: "local",
      ref: FONT_REFERENCE,
      status: "inlined",
      mime: "font/woff2",
      resolved: font,
    },
  ]);
  assert.deepStrictEqual(result.warnings, [], "成功内嵌不产生 warning");
});

test("references resolve against the given base directory", function () {
  const directory = tempDirectory();
  const font = writeFont(directory);
  const css = "a{background:url(" + FONT_REFERENCE + ")}";

  const elsewhere = resolve(css, directory + path.sep + "nested");

  assert.strictEqual(elsewhere.css, css, "base directory 之外的文件不该被误读");
  assert.strictEqual(elsewhere.items[0].status, "failed");
  assert.strictEqual(elsewhere.warnings.length, 1);

  const fromBase = resolve(css, directory);

  assert.deepStrictEqual(fromBase.items[0].resolved, font);
  assert.ok(fromBase.css.includes("url(data:font/woff2;base64,"));
});

test("a missing file keeps the original reference and warns with a readable path", function () {
  const directory = tempDirectory();

  const result = resolve("a{background:url('fonts/missing.woff2')}", directory);

  assert.strictEqual(result.css, "a{background:url('fonts/missing.woff2')}");
  assert.strictEqual(result.warnings.length, 1);
  assert.ok(result.warnings[0].startsWith("CSS 资源无法内嵌，保留原引用："), result.warnings[0]);
  assert.ok(result.warnings[0].includes("fonts/missing.woff2"), result.warnings[0]);
  assert.deepStrictEqual(result.items, [
    { kind: "css-resource", source: "local", ref: "fonts/missing.woff2", status: "failed" },
  ]);
});

test("external urls, fragments, data URIs and other schemes are left alone", function () {
  const directory = tempDirectory();
  const source = [
    'a{background:url("https://example.com/a.woff2")}',
    "b{background:url(//cdn.example.com/b.woff2)}",
    "c{background:url(#gradient)}",
    "d{background:url(data:font/woff2;base64,AAAA)}",
    "e{background:url(file:///C:/fonts/c.woff2)}",
  ].join("");

  const result = resolve(source, directory);

  assert.strictEqual(result.css, source);
  assert.deepStrictEqual(result.items, []);
  assert.deepStrictEqual(result.warnings, []);
});

test("extractCssReferences lists exactly the references the resolver would handle", function () {
  const source =
    '@font-face{src:url("fonts/A.woff2") format("woff2"),url(fonts/B.woff)}' +
    "a{background:url(https://example.com/c.png)}" +
    "b{background:url(#x)}";

  assert.deepStrictEqual(extractCssReferences(source), ["fonts/A.woff2", "fonts/B.woff"]);
});