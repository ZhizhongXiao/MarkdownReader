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
 *                           (+ math compat) → plantuml → mermaid → footnote → MarkdownReader 扩展
 * 去掉的理由：front matter 属性面板（AGENTS §6 不启用）、upstream TOC exporter（MarkdownReader
 * 自建 TOC）、highlight.js（后续决策）。它们只影响各自产物的存在与否，不改变其余插件的相对顺序
 * 与 token 语义。
 *
 * mermaid：**不**直接 require 上游 markdown-it-mermaid.js。上游用同步 try/catch 包 mermaid 11 的
 * async parse()，实测非法输入会以 rejected Promise 变成未捕获异常（进程 exit 1，破坏单 JSON
 * envelope 协议），并且会把浏览器 runtime（约 7.17MB bundle）打进 CLI。因此只复刻其 recognition
 * predicate 与容器 HTML，理由与证据见 extensions/mermaid_export.js。
 *
 * 基础配置跟随 KEEP contract：html:true、breaks:false、typographer 关闭、linkify 打开但关闭
 * fuzzy（裸文件名与版本号必须保持文本，不能被 linkify 变成 punycode 域名）。
 */

const MarkdownIt = require("markdown-it");
const markdownItAnchor = require("markdown-it-anchor");
const markdownItCheckbox = require("markdown-it-checkbox");
const markdownItFootnote = require("markdown-it-footnote");
const markdownItMark = require("markdown-it-mark");
const calloutsModule = require("markdown-it-obsidian-callouts");
const { markdownItMathCompat } = require("../extensions/math_compat");
const { markdownItMermaidExport } = require("../extensions/mermaid_export");
const { markdownItObsidianTagUnicode } = require("../extensions/obsidian_tag_unicode");
const { markdownItWikilinkStaticExport } = require("../extensions/obsidian_wikilink_export");
const {
  markdownItPlantumlExport,
  DEFAULT_PLANTUML_SERVER,
} = require("../extensions/plantuml_export");
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
    // \(…\) / \[…\] / begin-end 是 pinned 上游没有的 delimiter：只补解析，并 push 上游的
    // math_inline / math_block token 类型，渲染仍由上游 KaTeX renderer 完成。
    // options.math=false 时两者一起关闭，避免出现无 renderer 的 math token。
    md.use(markdownItMathCompat);
  }

  // plantuml 与 mermaid 的注册位置与上游 markdown-pdf.js 一致（plantuml 先，mermaid 后）。
  // mermaid 覆写 fence renderer，因此必须在 plantuml 的 fence→token 转换之后注册。
  // server URL 只有一个来源：options.plantuml_server 或 DEFAULT_PLANTUML_SERVER。
  md.use(markdownItPlantumlExport, { server: options.plantuml_server || DEFAULT_PLANTUML_SERVER });
  md.use(markdownItMermaidExport);

  // 3) MarkdownReader 薄兼容扩展：必须在上游对应插件之后注册（依赖其 token 类型/rules）。
  //    footnote 是 MarkdownReader-owned：pinned 上游没有 footnote 实现。
  md.use(markdownItFootnote);
  md.use(markdownItObsidianTagUnicode);
  md.use(markdownItWikilinkStaticExport);

  return { md: md, mathEnabled: mathEnabled };
}

module.exports = { createRenderer: createRenderer };
