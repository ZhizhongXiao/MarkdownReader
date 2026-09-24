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
 *   - href 变成指向目标名的 fragment（encodeURI(dest)）：非空、可解码识别目标；
 *   - 不猜测文件路径、不假设目标存在、不调用编辑器 API。
 *
 * Phase 4B 接入 document_map / `.md → .html` 关系后，只需替换本文件里 href 的构造。
 */

function markdownItWikilinkStaticExport(md) {
  md.renderer.rules.wikilink = function (tokens, index) {
    const token = tokens[index];
    const dest = token.meta && token.meta.dest ? String(token.meta.dest) : "";
    const display = md.utils.escapeHtml(token.content || dest);
    const target = encodeURI(dest).replace(/#/g, "%23");
    return (
      '<a class="obsidian-wikilink" data-href="' +
      md.utils.escapeHtml(dest) +
      '" href="#' +
      target +
      '">' +
      display +
      "</a>"
    );
  };
}

module.exports = { markdownItWikilinkStaticExport: markdownItWikilinkStaticExport };
