"use strict";

/**
 * 资源收集（Phase 5A）：parse 之后、render 之前一次性处理「需要资源层的引用」。
 *
 * 边界（沿用 K13 既有语义，不得扩大）：
 *   - **只处理 Markdown image token**；raw HTML（html_inline / html_block）里的 <img src>
 *     保持原样，绝不扫描最终 HTML —— 否则作者写在原始 HTML 里的行为会被悄悄改变；
 *   - data: / http(s): / 协议相对 / 其它 scheme 不属于本地资源（远程抓取属 5C），只记 manifest；
 *   - 读不到的本地文件：保留原引用 + 可读路径 warning。
 *
 * KaTeX（K21）：只有出现数学 token 时才把样式（字体已内嵌）放进 resources.styles。
 * Mermaid（5B/AGENTS §9）：只有文档真的含 Mermaid 时才把 vendored runtime 放进 resources.scripts。
 *   识别复用 4C 的唯一 predicate（extensions/mermaid_export.js::isMermaidFence）；不能用 token.meta
 *   标记，因为那个标记是 fence **renderer** 在 render 阶段写上的，而 collector 跑在 render 之前。
 */

const path = require("path");
const { isMermaidFence } = require("../extensions/mermaid_export");
const { createLocalFileReader } = require("./local_file");
const { loadKatexStyle } = require("./katex_assets");
const { loadMermaidRuntime } = require("./mermaid_runtime");

const IMAGE_KIND = "image";
const MATH_TOKEN_TYPES = ["math_inline", "math_block"];
const MISSING_IMAGE_WARNING = "图片无法内嵌，保留原引用：";

// Windows 绝对路径（C:/dir/a.png）必须先判：否则会被通用 scheme 规则误判成 other-scheme。
// 顺序与旧 production renderer 的 resolveImageSource 一致。
const ABSOLUTE_WINDOWS = /^[a-zA-Z]:[\\/]/;

function classifySource(reference) {
  const raw = String(reference === undefined || reference === null ? "" : reference);
  if (/^data:/i.test(raw)) {
    return "data";
  }
  if (/^(https?:)?\/\//i.test(raw)) {
    return "remote";
  }
  if (ABSOLUTE_WINDOWS.test(raw)) {
    return "local";
  }
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(raw)) {
    return "other-scheme";
  }
  return "local";
}

function walkTokens(tokens, visit) {
  for (const token of tokens || []) {
    visit(token);
    if (token.children && token.children.length) {
      walkTokens(token.children, visit);
    }
  }
}

function collectImageToken(token, baseDirectory, reader, warnings, items) {
  for (const attribute of token.attrs || []) {
    if (attribute[0] !== "src") {
      continue;
    }
    const reference = String(attribute[1] === undefined || attribute[1] === null ? "" : attribute[1]);
    const source = classifySource(reference);
    if (source !== "local") {
      items.push({ kind: IMAGE_KIND, source: source, ref: reference, status: "kept" });
      continue;
    }
    const file = reader.read(reference, baseDirectory, warnings, MISSING_IMAGE_WARNING);
    if (!file) {
      items.push({ kind: IMAGE_KIND, source: "local", ref: reference, status: "failed" });
      continue;
    }
    attribute[1] = file.dataUri;
    items.push({
      kind: IMAGE_KIND,
      source: "local",
      ref: reference,
      status: "inlined",
      mime: file.mimeType,
      resolved: file.absolute,
    });
  }
}

function collectResources(tokens, context) {
  const items = [];
  const styles = [];
  const scripts = [];
  const warnings = [];
  const settings = context || {};
  const sourcePath = settings.source_path || "";
  const reader = createLocalFileReader();
  // 相对图片路径需要有源文件上下文；没有上下文时不做解析（也不报 warning）。
  const baseDirectory = sourcePath ? path.dirname(sourcePath) : "";
  let hasMathTokens = false;
  let hasMermaidFence = false;

  walkTokens(tokens, function (token) {
    if (token.type === "image" && baseDirectory) {
      collectImageToken(token, baseDirectory, reader, warnings, items);
    }
    if (MATH_TOKEN_TYPES.indexOf(token.type) >= 0) {
      hasMathTokens = true;
    }
    if (token.type === "fence" && isMermaidFence(token.info, token.content)) {
      hasMermaidFence = true;
    }
  });

  // KaTeX 载荷只取决于数学 token（K21），与源文件上下文无关。
  if (hasMathTokens) {
    const style = loadKatexStyle(reader, warnings);
    if (style) {
      styles.push({ id: style.id, css: style.css });
      for (const item of style.items) {
        items.push(item);
      }
    }
  }

  // Mermaid 载荷只取决于 fence 识别（AGENTS §9），与源文件上下文无关。
  if (hasMermaidFence) {
    const runtime = loadMermaidRuntime(warnings);
    if (runtime) {
      scripts.push({
        id: runtime.id,
        version: runtime.version,
        script: runtime.script,
        boot: runtime.boot,
      });
      items.push(runtime.item);
    }
  }

  return { items: items, styles: styles, scripts: scripts, warnings: warnings };
}

module.exports = {
  collectResources: collectResources,
  IMAGE_KIND: IMAGE_KIND,
  MISSING_IMAGE_WARNING: MISSING_IMAGE_WARNING,
};
