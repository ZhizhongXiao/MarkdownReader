"use strict";

/**
 * MarkdownReader renderer protocol (Phase 3).
 *
 * 调用方与 renderer 之间只有这份 JSON 契约，不共享内存对象：
 *   - 成功与失败都只输出一个 JSON envelope 到 stdout；
 *   - 诊断、日志与堆栈一律走 stderr，绝不混进 stdout。
 *
 * 输入（stdin）：
 *   { "markdown": "...", "options": {}, "context": { "source_path": "",
 *     "output_path": "", "document_map": {} } }
 */

const PROTOCOL_VERSION = 1;

const FEATURE_KEYS = [
  "katex",
  "mermaid",
  "plantuml",
  "checkbox",
  "callout",
  "wikilink",
  "mark",
  "obsidian_tag",
];

class ProtocolError extends Error {
  constructor(code, message, detail) {
    super(message);
    this.code = code;
    this.detail = detail === undefined ? "" : String(detail);
  }
}

function emptyFeatures() {
  const features = {};
  for (const key of FEATURE_KEYS) {
    features[key] = false;
  }
  return features;
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validateRequest(value) {
  if (!isPlainObject(value)) {
    throw new ProtocolError("invalid_request", "请求必须是一个 JSON 对象。");
  }
  if (typeof value.markdown !== "string") {
    throw new ProtocolError("invalid_request", "缺少 string 字段 markdown。");
  }
  const options = value.options === undefined ? {} : value.options;
  if (!isPlainObject(options)) {
    throw new ProtocolError("invalid_request", "options 必须是对象。");
  }
  const context = value.context === undefined ? {} : value.context;
  if (!isPlainObject(context)) {
    throw new ProtocolError("invalid_request", "context 必须是对象。");
  }
  return { markdown: value.markdown, options, context };
}

function okEnvelope(payload) {
  return {
    protocol_version: PROTOCOL_VERSION,
    ok: true,
    html: payload.html,
    headings: payload.headings,
    features: payload.features,
    warnings: payload.warnings,
  };
}

function errorEnvelope(code, message, detail) {
  return {
    protocol_version: PROTOCOL_VERSION,
    ok: false,
    error: { code, message, detail: detail === undefined ? "" : String(detail) },
  };
}

function serialize(envelope) {
  return JSON.stringify(envelope) + "\n";
}

module.exports = {
  PROTOCOL_VERSION,
  FEATURE_KEYS,
  ProtocolError,
  emptyFeatures,
  validateRequest,
  okEnvelope,
  errorEnvelope,
  serialize,
};
