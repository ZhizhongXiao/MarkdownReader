"use strict";

/**
 * Unicode compatibility scanner 的单元测试（node:test）。
 *
 * 目的：证明 MarkdownReader 的 compatibility extension 只接管**含上游 ASCII 集之外字符**的 tag
 * candidate —— 纯 ASCII tag 仍由 pinned 上游的 obsidian_tag rule 解析（ownership 归上游）。
 */

const assert = require("node:assert");
const { test } = require("node:test");

const { scanTagCandidate } = require("../extensions/obsidian_tag_unicode.js");

const PURE_ASCII = ["#note", "#project/sub", "#a_b", "#abc-1", "#A9/x_y-z"];
const NEEDS_UNICODE = ["#笔记", "#项目/子项", "#abc中文", "#abc/项目", "#项目/sub", "#abc_中"];

test("pure ASCII candidates are left to the upstream rule", function () {
  for (const text of PURE_ASCII) {
    const candidate = scanTagCandidate(text, 0);
    assert.strictEqual(candidate.needsUnicodeCompat, false, text);
    assert.ok(candidate.length > 0, text);
  }
});

test("Unicode or mixed candidates are taken over by the compatibility rule", function () {
  for (const text of NEEDS_UNICODE) {
    assert.strictEqual(scanTagCandidate(text, 0).needsUnicodeCompat, true, text);
  }
});

test("mixed candidates are scanned as a whole and non-tags yield zero length", function () {
  const mixed = scanTagCandidate("#abc中文 rest", 0);
  assert.strictEqual(mixed.length, "abc中文".length);
  assert.strictEqual(mixed.needsUnicodeCompat, true);

  for (const text of ["#", "# 标题", "#!", "#\n"]) {
    assert.strictEqual(scanTagCandidate(text, 0).length, 0, text);
  }
});
