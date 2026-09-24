#!/usr/bin/env node
"use strict";

/**
 * MarkdownReader renderer entry（Phase 3）。
 *
 * 用法：
 *   node renderer.cjs          从 stdin 读 JSON 请求，向 stdout 写一个 JSON envelope
 *   node renderer.cjs --info   报告协议版本、上游位置与被复用的上游源文件
 *
 * 约定：stdout 只有 JSON；诊断与堆栈走 stderr；失败时 exit 1 并给出 error envelope。
 * 不使用 process.exit()：Windows 下大输出（例如 KaTeX）可能被截断，改用 exitCode。
 */

const {
  PROTOCOL_VERSION,
  ProtocolError,
  validateRequest,
  okEnvelope,
  errorEnvelope,
  serialize,
} = require("./protocol");
const { createRenderer } = require("./upstream/create_renderer");
const { collectHeadings, headingAnchorFallback } = require("./document/headings");
const { detectFeatures } = require("./document/features");
const { transformDocumentLinks } = require("./document/links");
const { collectResources } = require("./resources/collector");
const upstreamPaths = require("./upstream/paths");

function emit(text, code) {
  process.stdout.write(text);
  process.exitCode = code;
}

function fail(code, message, detail) {
  process.stderr.write(
    "[renderer] " + code + ": " + message + (detail ? " (" + detail + ")" : "") + "\n",
  );
  emit(serialize(errorEnvelope(code, message, detail)), 1);
}

function renderRequest(request) {
  const warnings = [];
  const renderer = createRenderer({ options: request.options });
  // document 层职责（K14 的 id 非空保证）由 entry 组合，upstream/ 只负责上游与基础配置。
  renderer.md.use(headingAnchorFallback);

  if (!renderer.mathEnabled) {
    warnings.push("options.math=false：公式不会被渲染。");
  }

  const env = {};
  const tokens = renderer.md.parse(request.markdown, env);
  // document 层（Phase 4B）：parse 之后、render 之前只跑一次 —— `.md → .html` 重写与
  // WikiLink 目标解析都写进 token，避免 heading metadata + 正文两次 inline 渲染造成重复 warning。
  const documentLinks = transformDocumentLinks(tokens, request.context);
  // 资源层（Phase 5A）：同样在 parse 后、render 前只跑一次；只处理 Markdown image token
  // （raw HTML 里的引用保持原样），并把需要 assembler 注入的 CSS 放进 resources.styles。
  const resources = collectResources(tokens, request.context);
  const headings = collectHeadings(renderer.md, tokens, env);
  const html = renderer.md.renderer.render(tokens, renderer.md.options, env);

  // features 由 token 语义驱动（Phase 4A/4B/4C），不再依赖 HTML substring。
  return {
    html: html,
    headings: headings,
    features: detectFeatures(html, tokens),
    warnings: warnings.concat(documentLinks.warnings, resources.warnings),
    resources: {
      items: resources.items,
      styles: resources.styles,
      scripts: resources.scripts,
    },
  };
}

function readStdin() {
  return new Promise(function (resolve, reject) {
    let raw = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", function (chunk) {
      raw += chunk;
    });
    process.stdin.on("end", function () {
      resolve(raw);
    });
    process.stdin.on("error", reject);
  });
}

async function main() {
  if (process.argv.slice(2).indexOf("--info") >= 0) {
    // ok 反映真实健康状况：provenance 不成立或缺少上游源文件时 --info 也必须失败。
    const described = upstreamPaths.describe();
    const healthy = described.missing_sources.length === 0 && described.provenance_ok;
    const info = Object.assign({ protocol_version: PROTOCOL_VERSION, ok: healthy }, described);
    emit(serialize(info), healthy ? 0 : 1);
    return;
  }

  let raw = "";
  try {
    raw = await readStdin();
  } catch (error) {
    fail("input_read_failed", "无法读取 stdin。", error.message);
    return;
  }
  if (!raw.trim()) {
    fail("input_empty", "stdin 为空：请传入 JSON 请求。");
    return;
  }

  let parsed = null;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    fail("invalid_json", "stdin 不是合法 JSON。", error.message);
    return;
  }

  let request = null;
  try {
    request = validateRequest(parsed);
  } catch (error) {
    fail(
      error instanceof ProtocolError ? error.code : "invalid_request",
      error && error.message ? error.message : String(error),
      error instanceof ProtocolError ? error.detail : "",
    );
    return;
  }

  try {
    emit(serialize(okEnvelope(renderRequest(request))), 0);
  } catch (error) {
    fail(
      "render_failed",
      "渲染失败。",
      error && error.stack ? String(error.stack).split("\n")[0] : String(error),
    );
  }
}

main().catch(function (error) {
  fail("internal_error", "renderer 内部错误。", error && error.message ? error.message : String(error));
});
