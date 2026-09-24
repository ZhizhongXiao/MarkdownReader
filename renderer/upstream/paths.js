"use strict";

/**
 * pinned vscode-office 的位置，以及「被复用的上游源文件」清单。
 *
 * 真正的装载发生在 upstream/create_renderer.js，并且必须使用**字面量** require 路径，
 * 这样 bundler 才能把它们打进产物；动态 require 会留在运行时，重新引入 sibling module
 * resolution 问题（上游目录里没有 node_modules）。
 *
 * 因此本模块只负责三件事：报告位置、构建前检查缺失、给 entry --info 提供数据。
 */

const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const UPSTREAM_ROOT = path.join(REPO_ROOT, "upstream", "vscode-office");
const PIN_MANIFEST = path.join(REPO_ROOT, "upstream", "pin.json");

// 相对 UPSTREAM_ROOT，与 create_renderer.js 里的字面量 require 一一对应。
const REUSED_SOURCES = [
  "src/service/markdown/ext/markdown-it-obsidian.js",
  "src/service/markdown/ext/markdown-it-katex.js",
];

function missingSources() {
  return REUSED_SOURCES.filter(function (relative) {
    return !fs.existsSync(path.join(UPSTREAM_ROOT, relative));
  });
}

function pinnedCommit() {
  try {
    const pin = JSON.parse(fs.readFileSync(PIN_MANIFEST, "utf8"));
    return pin.pinned_commit || "";
  } catch (error) {
    return "";
  }
}

function describe() {
  return {
    upstream_root: UPSTREAM_ROOT,
    pinned_commit: pinnedCommit(),
    reused_sources: REUSED_SOURCES.slice(),
    missing_sources: missingSources(),
  };
}

module.exports = {
  REPO_ROOT: REPO_ROOT,
  UPSTREAM_ROOT: UPSTREAM_ROOT,
  PIN_MANIFEST: PIN_MANIFEST,
  REUSED_SOURCES: REUSED_SOURCES,
  missingSources: missingSources,
  pinnedCommit: pinnedCommit,
  describe: describe,
};
