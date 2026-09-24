"use strict";

/**
 * 建立 MarkdownReader 的 markdown-it 实例，并复用 pinned vscode-office 的 Markdown 实现。
 *
 * 复用边界：复用「Markdown 语义实现」，不复制「完整导出应用」。上游 markdown-pdf.js 混了
 * vscode.Uri、template、CSS、mermaid runtime 与 pdf/docx 导出，因此不作为入口。
 *
 * 插件顺序与上游 markdown-pdf.js 一致，去掉我们明确拒绝的部分：
 *   upstream: frontMatterExport → obsidian → obsidianCallouts → mark → checkbox → anchor
 *             → toc → katex → plantuml → mermaid
 *   adapter :               obsidian → obsidianCallouts → mark → checkbox → anchor → katex
 * 去掉的理由：front matter 属性面板（AGENTS §6 不启用）、upstream TOC exporter（MarkdownReader
 * 自建 TOC）、plantuml/mermaid（Phase 4B/5）、highlight.js（后续决策）。它们只影响各自产物的
 * 存在与否，不改变其余插件的相对顺序与 token 语义。
 *
 * 基础配置跟随 KEEP contract：html:true、breaks:false、typographer 关闭、linkify 打开但关闭
 * fuzzy（裸文件名与版本号必须保持文本，不能被 linkify 变成 punycode 域名）。
 */

const MarkdownIt = require("markdown-it");
const markdownItAnchor = require("markdown-it-anchor");
const markdownItCheckbox = require("markdown-it-checkbox");
const markdownItMark = require("markdown-it-mark");
const calloutsModule = require("markdown-it-obsidian-callouts");
const { markdownItObsidianTagUnicode } = require("../extensions/obsidian_tag_unicode");
const { markdownItWikilinkStaticExport } = require("../extensions/obsidian_wikilink_export");
const { missingSources } = require("./paths");

// 上游 callouts 同时提供 ESM 与 CJS 入口；这里兼容两种 interop 形态。
const markdownItObsidianCallouts = calloutsModule && calloutsModule.default ? calloutsModule.default : calloutsModule;

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

  // 1) 上游插件（顺序与 markdown-pdf.js 相同）
  md.use(upstreamObsidian);
  md.use(markdownItObsidianCallouts);
  md.use(markdownItMark);
  md.use(markdownItCheckbox);
  md.use(markdownItAnchor);

  const mathEnabled = options.math !== false;
  if (mathEnabled) {
    md.use(upstreamKatex);
  }

  // 2) MarkdownReader 薄兼容扩展：必须在上游对应插件之后注册（依赖其 token 类型/rules）。
  md.use(markdownItObsidianTagUnicode);
  md.use(markdownItWikilinkStaticExport);

  return { md: md, mathEnabled: mathEnabled };
}

module.exports = { createRenderer: createRenderer };
