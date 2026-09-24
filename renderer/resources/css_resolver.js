"use strict";

/**
 * 通用 CSS 资源 resolver（Phase 5A）。
 *
 * 与 Theme 无关：输入一段 CSS 与它的 base directory，处理 url(...)：
 *   - 相对路径 → 本地文件内嵌为 data URI（复用 local_file reader）；
 *   - data: / 绝对 URL / fragment → 原样保留（网络抓取属 5C）；
 *   - 读取失败 → 保留原引用 + warning（可读路径），并记入 manifest。
 *
 * 返回 { css, items }，items 进入 envelope 的 resources.items。
 * 目前接到 KaTeX CSS（dist/katex）；Phase 6/7 的 theme CSS 可直接复用本模块，
 * 但本阶段不建立 Theme Registry。
 *
 * 注意：只处理**明确交给资源层的 CSS**，不扫描 raw HTML 的 style 属性。
 */

const URL_FUNCTION = /url\(\s*(['"]?)([^'")]+)\1\s*\)/g;
const EXTERNAL = /^(data:|https?:|\/\/|#)/i;
const SCHEME = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;
const ABSOLUTE_WINDOWS = /^[a-zA-Z]:[\\/]/;

function isHandledReference(target) {
  if (!target || EXTERNAL.test(target)) {
    return false;
  }
  return !SCHEME.test(target) || ABSOLUTE_WINDOWS.test(target);
}

// 供 build 阶段列出一个 CSS 里**需要资源层处理**的引用（与运行期 resolver 共用同一套判断，
// 避免 build 与 runtime 各写一份「什么算 CSS 资源引用」）。
function extractCssReferences(css) {
  const source = String(css === undefined || css === null ? "" : css);
  const references = [];
  const seen = new Set();
  const pattern = new RegExp(URL_FUNCTION.source, URL_FUNCTION.flags);
  let match = pattern.exec(source);
  while (match) {
    const target = String(match[2]).trim();
    if (isHandledReference(target) && !seen.has(target)) {
      seen.add(target);
      references.push(target);
    }
    match = pattern.exec(source);
  }
  return references;
}

function resolveCssResources(css, baseDirectory, reader, warnings) {
  const items = [];

  const resolved = String(css === undefined || css === null ? "" : css).replace(
    URL_FUNCTION,
    function (match, _quote, reference) {
      const target = String(reference).trim();
      if (!isHandledReference(target)) {
        return match;
      }
      const file = reader.read(target, baseDirectory, warnings, "CSS 资源无法内嵌，保留原引用：");
      if (!file) {
        items.push({ kind: "css-resource", source: "local", ref: target, status: "failed" });
        return match;
      }
      items.push({
        kind: "css-resource",
        source: "local",
        ref: target,
        status: "inlined",
        mime: file.mimeType,
        resolved: file.absolute,
      });
      return "url(" + file.dataUri + ")";
    },
  );

  return { css: resolved, items: items };
}

module.exports = {
  resolveCssResources: resolveCssResources,
  extractCssReferences: extractCssReferences,
};
