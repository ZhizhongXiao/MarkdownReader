"use strict";

/**
 * 从 **token 语义** 推断 features（Phase 4A）。
 *
 * 不再用 html.includes(...) 判断本轮五项能力：raw HTML（<mark>、<input type=checkbox>、
 * <div class="callout">、<a class="obsidian-wikilink">、<span class="obsidian-tag">）不得让
 * feature 误报成「Markdown 扩展生效」。
 *
 * Phase 4A/4B：mark / checkbox / callout / wikilink / obsidian_tag 由上游 token 类型驱动。
 * Phase 4C：plantuml 由插件 token `uml_diagram` 驱动；mermaid 由 fence token 上的语义标记
 *   `token.meta.mr_mermaid` 驱动（识别 predicate 的唯一来源是 extensions/mermaid_export.js）。
 * katex 自 Phase 4B 起同样是 token 驱动：需要真实数学 token **且** 确实渲染出 KaTeX markup。
 */

const { emptyFeatures } = require("../protocol");

// 上游/插件产出的 token 类型 → feature
const TOKEN_FEATURES = {
  mark_open: "mark",
  checkbox_input: "checkbox",
  callout_open: "callout",
  wikilink: "wikilink",
  wikilink_embed: "wikilink",
  obsidian_tag: "obsidian_tag",
  // markdown-it-plantuml 的 token：裸 @startuml 块与 ```plantuml / ```puml 围栏都产出它。
  uml_diagram: "plantuml",
};

// 上游 KaTeX 插件与 MarkdownReader math compat 都 push 这两种 token 类型。
const MATH_TOKEN_TYPES = ["math_inline", "math_block"];

// Mermaid 没有专用 token 类型（pinned 上游覆写的是 fence renderer），因此 adapter 在 fence token
// 上写这个语义标记；features 只读标记，不重复实现识别逻辑。
const MERMAID_META_FLAG = "mr_mermaid";

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

  let hasMathTokens = false;
  walkTokens(tokens, function (token) {
    const key = TOKEN_FEATURES[token.type];
    if (key) {
      features[key] = true;
    }
    if (token.meta && token.meta[MERMAID_META_FLAG] === true) {
      features.mermaid = true;
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

module.exports = { detectFeatures: detectFeatures };
