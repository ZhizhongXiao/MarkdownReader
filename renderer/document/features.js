"use strict";

/**
 * 从 **token 语义** 推断 features（Phase 4A）。
 *
 * 不再用 html.includes(...) 判断本轮五项能力：raw HTML（<mark>、<input type=checkbox>、
 * <div class="callout">、<a class="obsidian-wikilink">、<span class="obsidian-tag">）不得让
 * feature 误报成「Markdown 扩展生效」。
 *
 * 仍 pending（Phase 4C/5）：mermaid、plantuml（未接插件，恒 false）。
 * katex 自 Phase 4B 起同样是 token 驱动：需要真实数学 token **且** 确实渲染出 KaTeX markup。
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

// 上游 KaTeX 插件与 MarkdownReader math compat 都 push 这两种 token 类型。
const MATH_TOKEN_TYPES = ["math_inline", "math_block"];

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

  let hasMathTokens = false;
  walkTokens(tokens, function (token) {
    const key = TOKEN_FEATURES[token.type];
    if (key) {
      features[key] = true;
    }
    if (MATH_TOKEN_TYPES.indexOf(token.type) >= 0) {
      hasMathTokens = true;
    }
  });

  // KaTeX：数学 token 与 KaTeX markup 必须同时成立。raw HTML 里手写的
  // <span class="katex"> 不是公式；坏公式（katex-error）仍是 KaTeX 产物。
  features.katex = hasMathTokens && String(html || "").includes('class="katex');
  return features;
}

module.exports = { detectFeatures: detectFeatures, PENDING_KEYS: PENDING_KEYS };
