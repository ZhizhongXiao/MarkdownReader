"use strict";

/**
 * Mermaid recognition predicate 的单元测试（node:test）。
 *
 * 目的：证明 MarkdownReader 复刻的 predicate 与 pinned vscode-office
 * (908258dafc827ce0475fe7671d414914fbd3867b, src/service/markdown/ext/markdown-it-mermaid.js)
 * 的识别语义一致，包括几个容易写错的细节：markdown-it 不 trim token.info、graph 方向大小写敏感、
 * 只有 graph 允许尾随分号、任何 fence 语言都可能因首行命中。
 *
 * 表来自 Phase 4C characterization（docs/MARKDOWN_COMPATIBILITY.md）。上游升级时重新审计这张表，
 * 而不是断言上游源码的具体写法。
 */

const assert = require("node:assert");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const { isMermaidFence } = require("../extensions/mermaid_export.js");

// [说明, info, content]；content 的首行都不命中 implicit 规则，用于隔离 info 比较本身。
const RECOGNISED = [
  ["explicit info word", "mermaid", "graph TD\nA-->B"],
  ["implicit gantt", "", "gantt\ntitle x"],
  ["implicit sequenceDiagram", "", "sequenceDiagram\nA->>B: hi"],
  ["implicit graph LR", "", "graph LR\nA-->B"],
  ["implicit graph TD with trailing semicolon", "", "graph TD;\nA-->B"],
  ["first line is trimmed before matching", "", "   graph TD\nA-->B"],
  ["any fence language may match by first line", "js", "gantt\ntitle x"],
];

const NOT_RECOGNISED = [
  ["info with trailing spaces is not the explicit form", "mermaid  ", "title\n只是代码"],
  ["info comparison is case sensitive", "Mermaid", "title\n只是代码"],
  ["info with attributes is not the explicit form", "mermaid title=x", "title\n只是代码"],
  ["graph direction is case sensitive", "", "graph lr\nA-->B"],
  ["graph with extra text after the semicolon", "", "graph LR; extra"],
  ["semicolon is only allowed for graph", "", "sequenceDiagram;"],
  ["flowchart is not in the predicate", "", "flowchart TB\nA-->B"],
  ["plain code", "", "const a = 1;"],
];

test("pinned upstream Mermaid fences are recognised", function () {
  for (const [label, info, content] of RECOGNISED) {
    assert.strictEqual(isMermaidFence(info, content), true, label);
  }
});

test("fences pinned upstream does not treat as Mermaid stay code", function () {
  for (const [label, info, content] of NOT_RECOGNISED) {
    assert.strictEqual(isMermaidFence(info, content), false, label);
  }
});

test("upstream Mermaid source is still present for auditing", function (t) {
  const repoRoot = path.resolve(__dirname, "..", "..");
  const relative = "upstream/vscode-office/src/service/markdown/ext/markdown-it-mermaid.js";
  if (!fs.existsSync(path.join(repoRoot, "upstream", "vscode-office"))) {
    return t.skip("upstream submodule 未初始化，无法核对 Mermaid 源文件位置。");
  }
  assert.ok(fs.existsSync(path.join(repoRoot, relative)), "predicate 的审计来源位置变了：" + relative);
});
