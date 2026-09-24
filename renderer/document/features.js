"use strict";

/**
 * 从渲染结果推断 features。
 *
 * Phase 3 只报告**已经接入**的语义，不去猜未接入的能力：
 *   plantuml / mermaid / checkbox / callout / mark 恒为 false，
 *   等 Phase 4 接入对应上游（或第三方）插件后在这里补齐 marker。
 *
 * 已知局限：marker 检测无法区分「插件产出」与「正文里的原始 HTML」。Phase 4 接入
 * mark/checkbox 时应改为按 token 检测，避免把 <mark> 原始 HTML 误报成 mark 扩展。
 */

const { emptyFeatures } = require("../protocol");

const ACTIVE_MARKERS = {
  katex: ['class="katex'],
  wikilink: ["obsidian-wikilink"],
  obsidian_tag: ["obsidian-tag"],
};

const NOT_WIRED_KEYS = ["plantuml", "mermaid", "checkbox", "callout", "mark"];

function detectFeatures(html) {
  const features = emptyFeatures();
  for (const key of Object.keys(ACTIVE_MARKERS)) {
    features[key] = ACTIVE_MARKERS[key].some(function (marker) {
      return String(html).includes(marker);
    });
  }
  for (const key of NOT_WIRED_KEYS) {
    features[key] = false;
  }
  return features;
}

module.exports = { detectFeatures: detectFeatures, NOT_WIRED_KEYS: NOT_WIRED_KEYS };
