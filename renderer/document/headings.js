"use strict";

/**
 * K14 heading metadata 通道（renderer adapter contract）。
 *
 * 保留的语义：数组顺序、level、anchor、text、inline_html、toc_inline_html。
 * 字段名沿用既有契约（Phase 3 不改名）。TOC 用的 inline HTML 会把链接降级为可见文本、
 * 图片降级为 alt 文本，使标题可以安全嵌进目录导航链接。
 *
 * anchor 来自 markdown-it-anchor（与上游同一实现、同一默认选项）；Phase 3 不打算保持旧
 * renderer 的精确 slug 文本 —— 判定标准是「关系契约」：id 非空、唯一、与正文一致。
 */

const RAW_TAG_RE = /<\/?([a-zA-Z][a-zA-Z0-9]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>/g;
const RAW_ALT_RE = /\balt\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>]+))/i;

function rawAltText(attributes) {
  const match = RAW_ALT_RE.exec(String(attributes));
  if (!match) {
    return "";
  }
  const value = match[1] !== undefined ? match[1] : match[2] !== undefined ? match[2] : match[3];
  return String(value).replace(/</g, "&lt;");
}

// 只降级 <a>/</a>/<img>，其余原始行内 HTML 原样保留。
function downgradeInlineHtml(html) {
  return String(html).replace(RAW_TAG_RE, function (tag, name, attributes) {
    const lower = String(name).toLowerCase();
    if (lower === "a") {
      return "";
    }
    if (lower === "img") {
      return rawAltText(attributes);
    }
    return tag;
  });
}

function renderTocInline(md, children, env) {
  let result = "";
  for (let index = 0; index < children.length; index += 1) {
    const token = children[index];
    if (token.type === "link_open" || token.type === "link_close") {
      continue;
    }
    if (token.type === "image") {
      const alt = md.renderer.renderInlineAsText(token.children || [], md.options, env);
      result += md.utils.escapeHtml(alt);
      continue;
    }
    if (token.type === "html_inline") {
      result += downgradeInlineHtml(token.content);
      continue;
    }
    const rule = md.renderer.rules[token.type];
    result += rule
      ? rule(children, index, md.options, env, md.renderer)
      : md.renderer.renderToken(children, index, md.options);
  }
  return result;
}

function collectHeadings(md, tokens, env) {
  const headings = [];
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token.type !== "heading_open") {
      continue;
    }
    const inline = tokens[index + 1];
    const hasInline = Boolean(inline) && inline.type === "inline";
    const text = hasInline ? String(inline.content).trim().replace(/\s+#+\s*$/, "") : "";
    headings.push({
      level: Number(String(token.tag).slice(1)),
      text: text,
      anchor: token.attrGet("id") || "",
      inline_html: hasInline ? md.renderer.renderInline(inline.children || [], md.options, env) : "",
      toc_inline_html: hasInline ? renderTocInline(md, inline.children || [], env) : "",
    });
  }
  return headings;
}

/**
 * K14 要求 heading id 非空。markdown-it-anchor 对空标题（例如 `##` 后面没有文字）会给出
 * 空 slug —— 那是上游默认行为。这里只补一个**确定性** fallback，不发明新的 slug 规则，
 * 也不复刻旧 renderer 的 slug 文本：同一个文档每次得到同样的 id，且不与已有 id 冲突。
 */
const FALLBACK_PREFIX = "heading-";

function headingAnchorFallback(md) {
  md.core.ruler.push("mr_heading_anchor_fallback", function (state) {
    const used = new Set();
    for (const token of state.tokens) {
      if (token.type === "heading_open" && token.attrGet("id")) {
        used.add(token.attrGet("id"));
      }
    }

    let position = 0;
    for (const token of state.tokens) {
      if (token.type !== "heading_open") {
        continue;
      }
      position += 1;
      if (token.attrGet("id")) {
        continue;
      }
      let attempt = position;
      let candidate = FALLBACK_PREFIX + attempt;
      while (used.has(candidate)) {
        attempt += 1;
        candidate = FALLBACK_PREFIX + attempt;
      }
      used.add(candidate);
      token.attrSet("id", candidate);
    }
    return true;
  });
}

module.exports = { collectHeadings: collectHeadings, headingAnchorFallback: headingAnchorFallback };
