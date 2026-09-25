"use strict";

/**
 * 作者 raw HTML 的 provenance 通道（Cutover C1）。
 *
 * 只做一件事：在 parse 之后、render 之前，从 `html_block` / `html_inline` token 上**记录**
 * 作者自己写进文档的**外部**子资源引用，并给出每个 ref 的 occurrence 数。
 *
 * 边界（严格）：
 *   - **不从最终 HTML 反推**：一旦从 html 反推，raw HTML 与 Markdown 生成的 HTML 就无法区分，
 *     Phase 5D 的四态模型会退化。必须趁 token 层还知道来源时记录；
 *   - **不是资源层**：不 fetch、不改 HTML、不进 `resources.items`（K13 保持原样）。产物走独立的
 *     additive 通道 `resources.author_references`（协议仍 v2）；
 *   - 只记录外部引用：`data:` / `about:` / `#` / 空引用不属于「外部」。
 *
 * 规则必须与 closure checker（tools/standalone_closure.py）的子资源定义**同构**，否则作者
 * raw HTML 文档会被判 failure。两侧由 `tests/fixtures/author_references.json` 强制对齐：
 * 同一批 fixture 在 node 侧与 pytest 侧各跑一次，任何漂移都会红。
 *
 * 已知对齐边界：实体解码覆盖 URL 里会出现的名字实体（&amp; &lt; &gt; &quot; &apos;）与数字引用；
 * checker 侧用 Python 的 `html.unescape` 全集，因此 fixture 只使用上述几种。
 */

const RAW_HTML_TOKEN_TYPES = ["html_block", "html_inline"];

// 与 checker 的 SUB_RESOURCE_ATTRIBUTES / SRCSET_ATTRIBUTES 一一对应。
const SUB_RESOURCE_ATTRIBUTES = {
  img: ["src"],
  script: ["src"],
  link: ["href"],
  source: ["src"],
  iframe: ["src"],
  embed: ["src"],
  object: ["data"],
  video: ["poster"],
};
const SRCSET_ATTRIBUTES = { img: ["srcset"], source: ["srcset"] };

// `<link rel>` 三档规则：fetching token 优先于 metadata token，未知/缺失/混合未知按 subresource。
const FETCHING_LINK_RELS = [
  "apple-touch-icon",
  "apple-touch-icon-precomposed",
  "icon",
  "manifest",
  "mask-icon",
  "modulepreload",
  "prefetch",
  "preload",
  "stylesheet",
];
const NON_FETCHING_LINK_RELS = [
  "alternate",
  "author",
  "bookmark",
  "canonical",
  "dns-prefetch",
  "help",
  "license",
  "me",
  "next",
  "pingback",
  "preconnect",
  "prev",
  "search",
  "tag",
  "webmention",
];

const INLINE_PREFIXES = ["data:", "about:", "#"];

const TAG_PATTERN = /<([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>/g;
const ATTRIBUTE_PATTERN = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+))/g;
const STYLE_ELEMENT_PATTERN = /<style\b[^>]*>([\s\S]*?)<\/style>/gi;
const SCRIPT_ELEMENT_PATTERN = /(<script\b[^>]*>)([\s\S]*?)(<\/script>)/gi;
const COMMENT_PATTERN = /<!--[\s\S]*?-->/g;
const CSS_URL_PATTERN = /url\(\s*(["']?)([^"'()]+)\1\s*\)/g;
const CSS_IMPORT_PATTERN = /@import\s+(["'])([^"']+)\1/g;

const NAMED_ENTITIES = { amp: "&", apos: "'", gt: ">", lt: "<", quot: '"' };

function decodeEntities(value) {
  return String(value).replace(
    /&(#[xX]?[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);/g,
    function (match, body) {
      if (body.charAt(0) === "#") {
        const hex = body.charAt(1) === "x" || body.charAt(1) === "X";
        const code = parseInt(body.slice(hex ? 2 : 1), hex ? 16 : 10);
        const valid = Number.isFinite(code) && code > 0 && code <= 0x10ffff;
        return valid ? String.fromCodePoint(code) : match;
      }
      const named = NAMED_ENTITIES[body.toLowerCase()];
      return named === undefined ? match : named;
    },
  );
}

function walkTokens(tokens, visit) {
  for (const token of tokens || []) {
    visit(token);
    if (token.children && token.children.length) {
      walkTokens(token.children, visit);
    }
  }
}

function parseAttributes(source) {
  const attributes = {};
  ATTRIBUTE_PATTERN.lastIndex = 0;
  let match = ATTRIBUTE_PATTERN.exec(source);
  while (match) {
    const raw = match[3] !== undefined ? match[3] : match[4] !== undefined ? match[4] : match[5];
    attributes[match[1].toLowerCase()] = decodeEntities(raw);
    match = ATTRIBUTE_PATTERN.exec(source);
  }
  return attributes;
}

function linkReferenceIsFetched(rel) {
  const raw = rel === undefined || rel === null ? "" : rel;
  const tokens = String(raw).toLowerCase().split(/\s+/).filter(Boolean);
  if (tokens.some((token) => FETCHING_LINK_RELS.indexOf(token) >= 0)) {
    return true;
  }
  const metadataOnly = tokens.every((token) => NON_FETCHING_LINK_RELS.indexOf(token) >= 0);
  return tokens.length === 0 || !metadataOnly;
}

/** `srcset` 按 HTML 解析算法走 token：URL 是非空白串，因此 data URI 里的逗号被保留。 */
function srcsetReferences(value) {
  const references = [];
  const text = String(value);
  let position = 0;
  while (position < text.length) {
    while (position < text.length && (/\s/.test(text[position]) || text[position] === ",")) {
      position += 1;
    }
    const urlMatch = text.slice(position).match(/^\S+/);
    if (!urlMatch) {
      break;
    }
    let url = urlMatch[0];
    position += url.length;
    if (url.endsWith(",")) {
      url = url.replace(/,+$/, "");
      if (url) {
        references.push(url);
      }
      continue;
    }
    for (;;) {
      while (position < text.length && /\s/.test(text[position])) {
        position += 1;
      }
      const descriptor = text.slice(position).match(/^\S+/);
      if (!descriptor) {
        break;
      }
      position += descriptor[0].length;
      if (descriptor[0].endsWith(",")) {
        break;
      }
    }
    references.push(url);
  }
  return references;
}

/**
 * `url()` 与字符串形式 `@import`，按出现位置排序。
 *
 * 通道只承诺**跨 fragment** 的首次出现顺序：checker 把 ref 当多重集消费（`_occurrences`），
 * 不看顺序。同一 CSS 片段内部的顺序不构成契约 —— checker 的 `_css_references` 是先收 `url()`
 * 再收字符串 `@import`，这里按索引排序只是「片段内更自然」的呈现，因此两侧不在此处对齐。
 */
function cssReferences(css, includeStringImports) {
  const found = [];
  CSS_URL_PATTERN.lastIndex = 0;
  let match = CSS_URL_PATTERN.exec(css);
  while (match) {
    found.push({ index: match.index, ref: match[2].trim() });
    match = CSS_URL_PATTERN.exec(css);
  }
  if (includeStringImports) {
    CSS_IMPORT_PATTERN.lastIndex = 0;
    match = CSS_IMPORT_PATTERN.exec(css);
    while (match) {
      found.push({ index: match.index, ref: match[2].trim() });
      match = CSS_IMPORT_PATTERN.exec(css);
    }
  }
  return found.sort((left, right) => left.index - right.index).map((entry) => entry.ref);
}

function isExternalReference(reference) {
  const value = String(reference).trim().toLowerCase();
  if (!value) {
    return false;
  }
  return !INLINE_PREFIXES.some((prefix) => value.startsWith(prefix));
}

/**
 * 扫描一段 raw HTML 文本（`html_block` / `html_inline` 的 content），返回其中的外部子资源引用。
 *
 * script 元素内容与 HTML 注释先被剥掉：前者在 HTML 里是 CDATA（不是标签），后者 HTMLParser 也不看；
 * 否则 `<!-- <img src=…> -->` 会声明一个最终 HTML 里并不存在的引用。
 */
function referencesInRawHtml(rawHtml) {
  const text = String(rawHtml === undefined || rawHtml === null ? "" : rawHtml);
  const withoutComments = text.replace(COMMENT_PATTERN, "");
  const cssText = (withoutComments.match(STYLE_ELEMENT_PATTERN) || []).join("\n");
  const tagText = withoutComments
    .replace(STYLE_ELEMENT_PATTERN, "")
    .replace(SCRIPT_ELEMENT_PATTERN, "$1$3");

  const found = [];
  TAG_PATTERN.lastIndex = 0;
  let match = TAG_PATTERN.exec(tagText);
  while (match) {
    const name = match[1].toLowerCase();
    const attributes = parseAttributes(match[2]);
    for (const attribute of SUB_RESOURCE_ATTRIBUTES[name] || []) {
      const value = attributes[attribute];
      if (!value) {
        continue;
      }
      if (name === "link" && !linkReferenceIsFetched(attributes.rel)) {
        continue;
      }
      found.push(value.trim());
    }
    for (const attribute of SRCSET_ATTRIBUTES[name] || []) {
      const value = attributes[attribute];
      if (!value) {
        continue;
      }
      for (const reference of srcsetReferences(value)) {
        found.push(reference);
      }
    }
    if (attributes.style) {
      for (const reference of cssReferences(attributes.style, false)) {
        found.push(reference);
      }
    }
    match = TAG_PATTERN.exec(tagText);
  }
  for (const reference of cssReferences(cssText, true)) {
    found.push(reference);
  }
  return found;
}

/**
 * 从 token 树上收集作者 raw HTML 的外部引用：每个 ref 一条，`count` 为 occurrence 数，
 * 顺序为文档中的**首次出现顺序**。普通文档返回 `[]`。
 */
function collectAuthorReferences(tokens) {
  const counts = new Map();
  walkTokens(tokens, function (token) {
    if (RAW_HTML_TOKEN_TYPES.indexOf(token.type) < 0) {
      return;
    }
    for (const reference of referencesInRawHtml(token.content)) {
      if (!isExternalReference(reference)) {
        continue;
      }
      counts.set(reference, (counts.get(reference) || 0) + 1);
    }
  });
  return Array.from(counts, function (entry) {
    return { ref: entry[0], count: entry[1] };
  });
}

module.exports = {
  collectAuthorReferences: collectAuthorReferences,
  referencesInRawHtml: referencesInRawHtml,
};
