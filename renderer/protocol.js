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
 *
 * v2 成功 envelope 始终带 resources（无资源时是空结构，不存在「有时有、有时没有」）：
 *   resources.items   = 资源 manifest：[{ kind, source, ref, status, mime?, resolved? }]
 *   resources.styles  = 需要 assembler 注入的 CSS：[{ id, css }]（目前只有 katex）
 *   resources.scripts = 需要 assembler 注入的脚本：[{ id, version, script, boot }]
 *                       （目前只有按需的 mermaid；5B 起是 v2 的 additive 通道，不升版本）
 * warnings 仍是**用户可读字符串数组**，只承载降级/缺失/不可读等需要用户注意的情况；
 * 成功内嵌不产生 warning —— 状态记在 manifest 里（v1 的 envelope 属旧 production renderer）。
 */

const PROTOCOL_VERSION = 2;

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

function emptyResources() {
  return { items: [], styles: [], scripts: [] };
}

// v2：resources 是**必在**字段；缺失或形状不对时归一成空结构，而不是让字段忽隐忽现。
// scripts 是 5B 的 additive 通道：仍在 v2 之内，因此「必在」规则同样适用。
function normalizeResources(value) {
  if (!isPlainObject(value)) {
    return emptyResources();
  }
  return {
    items: Array.isArray(value.items) ? value.items : [],
    styles: Array.isArray(value.styles) ? value.styles : [],
    scripts: Array.isArray(value.scripts) ? value.scripts : [],
  };
}

function okEnvelope(payload) {
  return {
    protocol_version: PROTOCOL_VERSION,
    ok: true,
    html: payload.html,
    headings: payload.headings,
    features: payload.features,
    warnings: payload.warnings,
    resources: normalizeResources(payload.resources),
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
  emptyResources,
  validateRequest,
  okEnvelope,
  errorEnvelope,
  serialize,
};
