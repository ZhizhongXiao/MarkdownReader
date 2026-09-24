"use strict";

/**
 * KaTeX 样式与字体（Phase 5A）。
 *
 * 运行期**不依赖 renderer/node_modules**：build 阶段把 katex.min.css 与它引用的字体复制到
 * dist/katex/（见 build/build.js），运行期用通用 CSS resolver 把字体内嵌成 data URI。
 * 因此「npm ci → npm run build → dist 完整」之后，renderer 可以独立产出带公式的 standalone HTML。
 *
 * 载荷纪律（K21）：只有文档真的出现数学 token 时才把样式交出去（由 collector 决定）。
 */

const fs = require("fs");
const path = require("path");
const { resolveCssResources } = require("./css_resolver");

const STYLE_ID = "katex";

// 资产目录的解析规则必须同时支持两种布局：
//   - 打包后：dist/renderer.cjs 与 dist/katex/ 同级；
//   - 源码布局：renderer/resources/*.js 对应 renderer/dist/katex/。
// 取第一个存在的候选，避免写死某一层的相对位置。
function resolveKatexAssetDirectory() {
  const candidates = [
    path.join(__dirname, "katex"),
    path.join(__dirname, "..", "dist", "katex"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, "katex.min.css"))) {
      return candidate;
    }
  }
  return candidates[candidates.length - 1];
}

const KATEX_ASSET_DIRECTORY = resolveKatexAssetDirectory();

let cachedStyle = null;

function resetKatexStyleCache() {
  cachedStyle = null;
}

function loadKatexStyle(reader, warnings) {
  if (cachedStyle) {
    return cachedStyle;
  }
  const cssPath = path.join(KATEX_ASSET_DIRECTORY, "katex.min.css");
  let css = "";
  try {
    css = fs.readFileSync(cssPath, "utf8");
  } catch (error) {
    // 降级：样式缺失不阻断转换，但必须让用户看到（K15）。不缓存，后续转换仍会重试。
    warnings.push("KaTeX 样式不可用（缺少构建产物 dist/katex/katex.min.css）：" + error.message);
    return null;
  }
  const resolved = resolveCssResources(css, KATEX_ASSET_DIRECTORY, reader, warnings);
  cachedStyle = { id: STYLE_ID, css: resolved.css, items: resolved.items };
  return cachedStyle;
}

module.exports = {
  loadKatexStyle: loadKatexStyle,
  resolveKatexAssetDirectory: resolveKatexAssetDirectory,
  resetKatexStyleCache: resetKatexStyleCache,
  KATEX_ASSET_DIRECTORY: KATEX_ASSET_DIRECTORY,
  STYLE_ID: STYLE_ID,
};
