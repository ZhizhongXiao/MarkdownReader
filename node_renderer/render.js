#!/usr/bin/env node
/**
 * MDViewer — Node.js Markdown renderer.
 *
 * Reads JSON from stdin:
 *   {"markdown": "...", "options": {"html": true, "math": true}}
 *
 * Outputs JSON to stdout:
 *   {"html": "...", "warnings": [], "assets": {"css": "..."}}
 *
 * Dependencies: markdown-it, markdown-it-footnote, markdown-it-texmath, katex
 */

const fs = require("fs");
const path = require("path");

// ── Read stdin ──────────────────────────────────────────────────
let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("readable", function () {
  let chunk;
  while ((chunk = process.stdin.read()) !== null) {
    raw += chunk;
  }
});
process.stdin.on("end", function () {
  try {
    const input = JSON.parse(raw);
    const result = render(input);
    process.stdout.write(JSON.stringify(result));
    process.exit(0);
  } catch (e) {
    process.stderr.write("Error: " + e.message + "\n");
    process.exit(1);
  }
});

// ── Renderer ────────────────────────────────────────────────────
function render(input) {
  const markdown = input.markdown || "";
  const options = input.options || {};
  const context = input.context || {};

  const warnings = [];
  const headings = [];

  // markdown-it with conservative defaults
  const MarkdownIt = require("markdown-it");
  const md = MarkdownIt({
    html: options.html !== false, // keep raw HTML (spans, etc.)
    breaks: false,
    linkify: true,
    typographer: false,
  });

  installHeadingIds(md, headings);

  try {
    md.use(require("markdown-it-footnote"));
  } catch (e) {
    warnings.push("markdown-it-footnote not available: " + e.message);
  }

  installDocumentLinkResolver(md, context, warnings);

  // TeX math extension (supports $...$ and $$...$$)
  let texmath;
  try {
    texmath = require("markdown-it-texmath");
    const katex = require("katex");
    md.use(texmath, {
      engine: katex,
      delimiters: ["dollars", "brackets", "beg_end"],
      katexOptions: {
        throwOnError: false,
      },
    });
  } catch (e) {
    warnings.push("markdown-it-texmath or katex not available: " + e.message);
    // Continue without math support
  }

  // Render Markdown → HTML
  const html = md.render(markdown);

  // Collect KaTeX CSS for embedding
  let css = "";
  try {
    const katex = require("katex");
    // katex CSS is bundled in the package — read it from dist/
    const cssPath = require.resolve("katex/dist/katex.min.css");
    css = inlineCssUrls(fs.readFileSync(cssPath, "utf8"), cssPath, warnings);
  } catch (e) {
    warnings.push("Cannot read katex CSS: " + e.message);
  }

  return {
    html: html,
    headings: headings,
    warnings: warnings,
    assets: {
      css: css,
    },
  };
}

function installDocumentLinkResolver(md, context, warnings) {
  const sourcePath = context.source_path || "";
  const outputPath = context.output_path || "";
  const rawDocumentMap = context.document_map || {};
  if (!sourcePath || !outputPath || typeof rawDocumentMap !== "object") {
    return;
  }

  const documentMap = new Map();
  Object.keys(rawDocumentMap).forEach(function (source) {
    documentMap.set(normalizeFsPath(source), rawDocumentMap[source]);
  });

  const originalLinkOpen = md.renderer.rules.link_open;
  md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
    const token = tokens[idx];
    const hrefIndex = token.attrIndex("href");
    if (hrefIndex >= 0) {
      const href = token.attrs[hrefIndex][1];
      const rewritten = rewriteDocumentHref(
        href,
        sourcePath,
        outputPath,
        documentMap,
        warnings,
      );
      token.attrs[hrefIndex][1] = rewritten;
    }

    if (originalLinkOpen) {
      return originalLinkOpen(tokens, idx, options, env, self);
    }
    return self.renderToken(tokens, idx, options);
  };
}

function rewriteDocumentHref(href, sourcePath, outputPath, documentMap, warnings) {
  if (!href || href.startsWith("#") || href.startsWith("//")) {
    return href;
  }
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(href)) {
    return href;
  }

  const match = href.match(/^([^?#]*)([?#].*)?$/);
  const hrefPath = match ? match[1] : href;
  const suffix = match && match[2] ? match[2] : "";
  let decodedPath = hrefPath;
  try {
    decodedPath = decodeURI(hrefPath);
  } catch (_error) {
    // Keep the original path; markdown-it will safely encode it later.
  }

  const extension = path.extname(decodedPath).toLowerCase();
  if (extension !== ".md" && extension !== ".markdown") {
    return href;
  }

  const targetSource = path.resolve(path.dirname(sourcePath), decodedPath);
  const targetOutput = documentMap.get(normalizeFsPath(targetSource));
  if (!targetOutput) {
    warnings.push("Markdown 链接目标未加入转换清单：" + href);
    return href;
  }

  let relativeOutput = path.relative(path.dirname(outputPath), targetOutput).replace(/\\/g, "/");
  if (!relativeOutput.startsWith(".") && !relativeOutput.startsWith("/")) {
    relativeOutput = "./" + relativeOutput;
  }
  return encodeURI(relativeOutput) + suffix;
}

function normalizeFsPath(value) {
  let normalized = path.resolve(String(value || "")).replace(/\\/g, "/");
  if (process.platform === "win32") {
    normalized = normalized.toLowerCase();
  }
  return normalized;
}

function installHeadingIds(md, headings) {
  const usedAnchors = new Set();
  let fallbackCounter = 0;

  function unique(anchor) {
    const base = anchor;
    let counter = 1;
    while (usedAnchors.has(anchor)) {
      counter += 1;
      anchor = base + counter;
    }
    usedAnchors.add(anchor);
    return anchor;
  }

  md.renderer.rules.heading_open = function (tokens, idx, options, env, self) {
    const token = tokens[idx];
    const inlineToken = tokens[idx + 1];
    const rawText =
      inlineToken && inlineToken.type === "inline"
        ? inlineToken.content.trim().replace(/\s+#+\s*$/, "")
        : "";

    let anchor = slugifyUnicode(rawText);
    if (!anchor) {
      fallbackCounter += 1;
      anchor = "_" + fallbackCounter;
    }
    anchor = unique(anchor);

    token.attrSet("id", anchor);
    headings.push({
      level: Number(token.tag.slice(1)),
      text: rawText,
      anchor: anchor,
    });

    return self.renderToken(tokens, idx, options);
  };
}

function slugifyUnicode(text, separator = "-") {
  const normalized = text.normalize("NFC").toLowerCase().replace(/\s+/g, separator);
  let result = "";

  for (const ch of normalized) {
    if (/[\p{L}\p{N}\p{M}]/u.test(ch) || ch === separator) {
      result += ch;
    } else {
      result += separator;
    }
  }

  const repeatedSeparators = new RegExp(escapeRegExp(separator) + "+", "g");
  result = result.replace(repeatedSeparators, separator);
  return trimSeparator(result, separator);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function trimSeparator(value, separator) {
  const escaped = escapeRegExp(separator);
  return value
    .replace(new RegExp("^" + escaped + "+"), "")
    .replace(new RegExp(escaped + "+$"), "");
}

function inlineCssUrls(css, cssPath, warnings) {
  const cssDir = path.dirname(cssPath);

  return css.replace(/url\((['"]?)(fonts\/[^'")]+)\1\)/g, function (_match, _quote, urlPath) {
    const fontPath = path.join(cssDir, urlPath);
    try {
      const ext = path.extname(fontPath).toLowerCase();
      const mimeTypes = {
        ".woff2": "font/woff2",
        ".woff": "font/woff",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
      };
      const mimeType = mimeTypes[ext] || "application/octet-stream";
      const data = fs.readFileSync(fontPath).toString("base64");
      return "url(data:" + mimeType + ";base64," + data + ")";
    } catch (e) {
      warnings.push("Cannot inline KaTeX font " + urlPath + ": " + e.message);
      return "url(" + urlPath + ")";
    }
  });
}
