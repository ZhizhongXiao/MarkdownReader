"use strict";

/**
 * 从 **token 语义** 推断 features（Phase 4A）。
 *
 * 不再用 html.includes(...) 判断本轮五项能力：raw HTML（<mark>、<input type=checkbox>、
 * <div class="callout">、<a class="obsidian-wikilink">、<span class="obsidian-tag">）不得让
 * feature 误报成「Markdown 扩展生效」。
 *
 * 仍 pending（Phase 4C/5）：mermaid、plantuml（未接插件，恒 false）。
 * katex 目前仍用 HTML marker 判断 —— 记录为 remaining migration（Phase 4B 改 token 判断）。
 */

const { emptyFeatures } = require("../protocol");

// 上游插件产出的 token 类型 → feature
const TOKEN_FEATURES = {
  mark_open: "mark",
  checkbox_input: "checkbox",
  callout_open: "callout",
  wikilink: "wikilink",
  wikilink_embed: "wikilink",
  obsidian_tag: "obsidian_tag",
};

const PENDING_KEYS = ["plantuml", "mermaid"];

function walkTokens(tokens, visit) {
  for (const token of tokens || []) {
    visit(token);
    if (token.children && token.children.length) {
      walkTokens(token.children, visit);
    }
  }
}

function detectFeatures(html, tokens) {
  const features = emptyFeatures();
  for (const key of PENDING_KEYS) {
    features[key] = false;
  }

  walkTokens(tokens, function (token) {
    const key = TOKEN_FEATURES[token.type];
    if (key) {
      features[key] = true;
    }
  });

  // 仍属 remaining migration：KaTeX 用 marker 判断（Phase 4B 改 token 判断）。
  features.katex = String(html || "").includes('class="katex');
  return features;
}

module.exports = { detectFeatures: detectFeatures, PENDING_KEYS: PENDING_KEYS };
