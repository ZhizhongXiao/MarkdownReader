"use strict";

/**
 * 建立 MarkdownReader 的 markdown-it 实例，并复用 pinned vscode-office 的 Markdown 实现。
 *
 * 复用边界（Phase 3）：复用「Markdown 语义实现」，不复制「完整导出应用」。
 * 上游 src/service/markdown/markdown-pdf.js 混了 vscode.Uri、template、CSS、mermaid
 * runtime 与 pdf/docx 导出，MarkdownReader 不需要这些 exporter 职责，因此不作为入口，
 * 也不为它建立 vscode shim。
 *
 * 基础配置跟随 MarkdownReader 的 KEEP contract：
 *   html: true、breaks: false、typographer 关闭、linkify 打开但关闭 fuzzy
 *   （裸文件名与版本号必须保持文本，不能被 linkify 变成 punycode 域名）。
 */

const MarkdownIt = require("markdown-it");
const markdownItAnchor = require("markdown-it-anchor");
const { missingSources } = require("./paths");

// 字面量 require：bundler 必须能看到这两个路径（见 paths.js 的说明）。
let upstreamObsidian = null;
let upstreamKatex = null;
try {
  upstreamObsidian = require("../../upstream/vscode-office/src/service/markdown/ext/markdown-it-obsidian.js");
  upstreamKatex = require("../../upstream/vscode-office/src/service/markdown/ext/markdown-it-katex.js");
} catch (error) {
  const missing = missingSources();
  throw new Error(
    "无法装载 pinned 上游 Markdown 模块" +
      (missing.length ? "（缺失：" + missing.join("、") + "）" : "") +
      "；请确认 upstream submodule 已初始化：git submodule update --init --recursive。原始错误：" +
      error.message,
  );
}

function createRenderer(config) {
  const settings = config || {};
  const options = settings.options || {};

  const md = MarkdownIt({
    html: options.html !== false,
    breaks: false,
    linkify: true,
    typographer: false,
  });
  md.linkify.set({ fuzzyLink: false });

  // 与上游一致：markdown-it-anchor 使用默认选项，不发明第二套 slug 规则。
  md.use(markdownItAnchor);

  // 上游自实现的 obsidian 语义（wikilink / wikilink embed / #tag）。
  md.use(upstreamObsidian);

  const mathEnabled = options.math !== false;
  if (mathEnabled) {
    md.use(upstreamKatex);
  }

  return { md: md, mathEnabled: mathEnabled };
}

module.exports = { createRenderer: createRenderer };
