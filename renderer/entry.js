#!/usr/bin/env node
"use strict";

/**
 * MarkdownReader renderer entry（Phase 3）。
 *
 * 用法：
 *   node renderer.cjs          从 stdin 读 JSON 请求，向 stdout 写一个 JSON envelope
 *   node renderer.cjs --server 持续收发带协议版本和 ID 的 JSONL 请求
 *   node renderer.cjs --info   报告协议版本、上游位置与被复用的上游源文件
 *
 * 约定：stdout 只有 JSON；诊断与堆栈走 stderr；失败时 exit 1 并给出 error envelope。
 * 不使用 process.exit()：Windows 下大输出（例如 KaTeX）可能被截断，改用 exitCode。
 */

const {
  PROTOCOL_VERSION,
  ProtocolError,
  validateRequest,
  errorEnvelope,
  serialize,
} = require("./protocol");
const { renderEnvelope } = require("./render_request");
const { serve } = require("./server");
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

  if (process.argv.includes("--server")) {
    await serve();
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
    emit(serialize(await renderEnvelope(request)), 0);
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
