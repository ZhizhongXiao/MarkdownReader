"use strict";

/**
 * MarkdownReader static-export adaptation：WikiLink 的 href。
 *
 * 上游（pinned vscode-office）把 WikiLink 渲染成
 *   <a class="obsidian-wikilink" data-href="dest" href="#">display</a>
 * 其中 href="#" 是**编辑器**行为（点击由 VS Code 侧处理），不足以作为静态导出链接。
 *
 * 本扩展只替换 export representation：
 *   - parser / token / alias 仍全部来自上游（token.meta.dest、token.content）；
 *   - document 层（Phase 4B）解析出唯一目标时给出 token.meta.export_href（同目录唯一
 *     .md/.markdown → 对应 .html，可带 fragment）；
 *   - 否则保留 Phase 4A 的 fragment fallback（encodeURI(dest)），不猜路径、不假设目标存在。
 */

function markdownItWikilinkStaticExport(md) {
  md.renderer.rules.wikilink = function (tokens, index) {
    const token = tokens[index];
    const meta = token.meta || {};
    const dest = meta.dest === undefined || meta.dest === null ? "" : String(meta.dest);
    const display = md.utils.escapeHtml(token.content || dest);
    const href = meta.export_href ? String(meta.export_href) : "#" + encodeURI(dest).replace(/#/g, "%23");
    return (
      '<a class="obsidian-wikilink" data-href="' +
      md.utils.escapeHtml(dest) +
      '" href="' +
      md.utils.escapeHtml(href) +
      '">' +
      display +
      "</a>"
    );
  };
}

module.exports = { markdownItWikilinkStaticExport: markdownItWikilinkStaticExport };
