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
const upstreamPaths = require("./upstream/paths");

// 已知但尚未由新 renderer 处理的 context 字段：产出 warning，而不是静默忽略。
const DEFERRED_CONTEXT_KEYS = ["document_map"];

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

function hasMeaningfulValue(value) {
  if (value === undefined || value === null) {
    return false;
  }
  if (typeof value !== "object" || Array.isArray(value)) {
    return true;
  }
  return Object.keys(value).length > 0;
}

function renderRequest(request) {
  const warnings = [];
  const renderer = createRenderer({ options: request.options });
  // document 层职责（K14 的 id 非空保证）由 entry 组合，upstream/ 只负责上游与基础配置。
  renderer.md.use(headingAnchorFallback);

  for (const key of DEFERRED_CONTEXT_KEYS) {
    if (hasMeaningfulValue(request.context[key])) {
      warnings.push("context." + key + " 尚未由新 renderer 处理（Phase 4）：已忽略。");
    }
  }
  if (!renderer.mathEnabled) {
    warnings.push("options.math=false：公式不会被渲染。");
  }

  const env = {};
  const tokens = renderer.md.parse(request.markdown, env);
  const headings = collectHeadings(renderer.md, tokens, env);
  const html = renderer.md.renderer.render(tokens, renderer.md.options, env);

  return { html: html, headings: headings, features: detectFeatures(html), warnings: warnings };
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
    const info = Object.assign(
      { protocol_version: PROTOCOL_VERSION, ok: true },
      upstreamPaths.describe(),
    );
    emit(serialize(info), upstreamPaths.missingSources().length > 0 ? 1 : 0);
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
