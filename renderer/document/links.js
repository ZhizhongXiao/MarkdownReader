"use strict";

/**
 * document 层：parse 之后、render 之前的一次性 token 转换。
 *
 * 为什么不是 renderer rule：新 adapter 会对 inline 内容渲染两次（collectHeadings 的 heading
 * metadata + 正文 render），renderer rule 里的改写与 warning 会重复触发。这里只跑一次：
 *   - 标准 Markdown `.md` / `.markdown` 链接 → 对应输出 `.html`（K12）
 *   - WikiLink 目标 → token.meta.export_href（只用 document_map，不搜文件系统）
 *   - warnings 在这里集中产生（heading 内的链接也因此只报一次）
 *
 * 只消费 context：source_path / output_path / document_map。
 * 改写规则与旧 production renderer（node_renderer/render.js）逐条一致：跳过 fragment / 协议相对 /
 * 其它 scheme，只处理 .md 与 .markdown，相对**输出目录**计算 ./ 前缀 + encodeURI，保留 query 与
 * fragment；未加入转换清单时保留原 href 并产出可读 warning，不使转换失败。
 */

const path = require("path");

const BACKSLASH_CHAR = String.fromCharCode(92);
const MARKDOWN_EXTENSIONS = [".md", ".markdown"];
const SCHEME_PREFIX = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;
const HREF_PARTS = /^([^?#]*)([?#].*)?$/;
const WIKILINK_TARGET_SUFFIXES = ["", ".md", ".markdown"];
const WIKILINK_WARNING = "Markdown 链接目标未加入转换清单：";

function toForwardSlashes(value) {
  return String(value).split(BACKSLASH_CHAR).join("/");
}

// 与文档关系表（Python 侧）保持同一匹配语义：绝对路径 + Windows 大小写不敏感。
function normalizeFsPath(value) {
  let normalized = toForwardSlashes(path.resolve(String(value || "")));
  if (process.platform === "win32") {
    normalized = normalized.toLowerCase();
  }
  return normalized;
}

// markdown-it 把链接目标规范化成百分号编码，但那不是作者写下的文字。
function decodeForDisplay(value) {
  const raw = value === undefined || value === null ? "" : String(value);
  try {
    return decodeURI(raw);
  } catch (_error) {
    return raw;
  }
}

function splitHref(href) {
  const match = HREF_PARTS.exec(href);
  return {
    pathPart: match ? match[1] : href,
    suffix: match && match[2] ? match[2] : "",
  };
}

function buildOutputLookup(documentMap) {
  const lookup = new Map();
  for (const key of Object.keys(documentMap)) {
    const output = documentMap[key];
    if (typeof output === "string" && output !== "") {
      lookup.set(normalizeFsPath(key), output);
    }
  }
  return lookup;
}

function outputForSource(lookup, candidatePath) {
  const output = lookup.get(normalizeFsPath(candidatePath));
  return typeof output === "string" && output !== "" ? output : "";
}

function relativeOutputHref(outputPath, targetOutput, suffix) {
  let relative = toForwardSlashes(path.relative(path.dirname(outputPath), targetOutput));
  if (!relative.startsWith(".") && !relative.startsWith("/")) {
    relative = "./" + relative;
  }
  return encodeURI(relative) + (suffix || "");
}

// K12：标准 Markdown 文档链接 → 本次转换产出的 .html。
function rewriteDocumentHref(href, sourcePath, outputPath, lookup, warnings) {
  if (!href || href.startsWith("#") || href.startsWith("//") || SCHEME_PREFIX.test(href)) {
    return href;
  }
  const parts = splitHref(href);
  let decodedPath = parts.pathPart;
  try {
    decodedPath = decodeURI(parts.pathPart);
  } catch (_error) {
    // 保留原路径：markdown-it 会安全地编码它。
  }
  const extension = path.extname(decodedPath).toLowerCase();
  if (MARKDOWN_EXTENSIONS.indexOf(extension) < 0) {
    return href;
  }
  const targetOutput = outputForSource(lookup, path.resolve(path.dirname(sourcePath), decodedPath));
  if (!targetOutput) {
    warnings.push(WIKILINK_WARNING + decodeForDisplay(href));
    return href;
  }
  return relativeOutputHref(outputPath, targetOutput, parts.suffix);
}

// WikiLink → 源文件同目录下唯一的 .md / .markdown 目标。解析不出唯一目标时不改 href：
// 保留 Phase 4A 的 fragment fallback，也不新增 warning（未选中 ≠ 错误）。
function resolveWikiTarget(token, sourcePath, outputPath, lookup) {
  const meta = token.meta || {};
  const dest = meta.dest === undefined || meta.dest === null ? "" : String(meta.dest);
  const hashIndex = dest.indexOf("#");
  const page = (hashIndex < 0 ? dest : dest.slice(0, hashIndex)).trim();
  const fragment = hashIndex < 0 ? "" : dest.slice(hashIndex + 1);
  if (!page) {
    return "";
  }
  const sourceDirectory = path.dirname(sourcePath);
  const targets = [];
  for (const suffix of WIKILINK_TARGET_SUFFIXES) {
    const output = outputForSource(lookup, path.resolve(sourceDirectory, page + suffix));
    if (output && targets.indexOf(output) < 0) {
      targets.push(output);
    }
  }
  if (targets.length !== 1) {
    return "";
  }
  const suffix = fragment ? "#" + encodeURI(fragment) : "";
  return relativeOutputHref(outputPath, targets[0], suffix);
}

// 与 features.js 的同名 helper 相同：只做 token 树深度遍历，不做语义判断。
function walkTokens(tokens, visit) {
  for (const token of tokens || []) {
    visit(token);
    if (token.children && token.children.length) {
      walkTokens(token.children, visit);
    }
  }
}

function rewriteLinkToken(token, sourcePath, outputPath, lookup, warnings) {
  for (const attribute of token.attrs || []) {
    if (attribute[0] !== "href" || typeof attribute[1] !== "string") {
      continue;
    }
    const rewritten = rewriteDocumentHref(attribute[1], sourcePath, outputPath, lookup, warnings);
    if (rewritten !== attribute[1]) {
      attribute[1] = rewritten;
    }
  }
}

function transformDocumentLinks(tokens, context) {
  const warnings = [];
  const settings = context || {};
  const sourcePath = settings.source_path || "";
  const outputPath = settings.output_path || "";
  const documentMap = settings.document_map;
  if (!sourcePath || !outputPath || !documentMap || typeof documentMap !== "object") {
    return { warnings: warnings };
  }
  const lookup = buildOutputLookup(documentMap);
  walkTokens(tokens, function (token) {
    if (token.type === "link_open") {
      rewriteLinkToken(token, sourcePath, outputPath, lookup, warnings);
      return;
    }
    if (token.type === "wikilink") {
      // 嵌入（![[]]）不是文档链接：它属于 Phase 5 资源层，这里不产出 export_href。
      const href = resolveWikiTarget(token, sourcePath, outputPath, lookup);
      if (href) {
        // 渲染由 extensions/obsidian_wikilink_export.js 消费。
        token.meta = Object.assign({}, token.meta, { export_href: href });
      }
    }
  });
  return { warnings: warnings };
}

module.exports = { transformDocumentLinks: transformDocumentLinks };
