"use strict";

/**
 * MarkdownReader Mermaid export adaptation（Phase 4C）。
 *
 * 语义来源（recognition predicate 逐条复刻）：
 *   pinned vscode-office 908258dafc827ce0475fe7671d414914fbd3867b
 *   src/service/markdown/ext/markdown-it-mermaid.js
 *
 * 为什么**不**直接 require 上游模块（有实测证据的取舍，见 docs/MARKDOWN_COMPATIBILITY.md）：
 *   - 上游模块 import 'mermaid'（11.x 浏览器向 runtime）：111 个包，打包后约 7.17MB / 1929 modules；
 *   - 它的 try { mermaid.parse(code) } catch {…} 与 mermaid 11 的 Promise API 不匹配：实测非法
 *     输入会 reject → 未捕获异常 → Node 进程 exit 1，会破坏 stdout 的单 JSON envelope 协议；
 *   - 上游的 <pre> 错误分支因此不可达，而 parse 的结果从未被使用。
 *   Phase 4C 只迁移 recognition 与 source container；syntax validation / render / runtime 属 Phase 5
 *   （AGENTS §9：Mermaid runtime 按需加入生成物）。
 *
 * D2（INTENTIONAL EXPORT HARDENING）：容器内容在 serialization 时 HTML-escape，使其在 runtime
 *   处理之前保持惰性文本；不变式是「交给 runtime 的 DOM 文本 == 作者原文」。
 */

const MERMAID_INFO_WORD = "mermaid";
const IMPLICIT_FIRST_LINES = ["gantt", "sequenceDiagram"];
const IMPLICIT_GRAPH_LINE = /^graph (?:TB|BT|RL|LR|TD);?$/;

// 唯一 predicate：features 与测试只消费它的结果（token.meta.mr_mermaid），不另写一套判断。
function isMermaidFence(info, content) {
  // markdown-it 不 trim token.info（实测 "```mermaid  " 得到 "mermaid  "），因此必须精确比较；
  // 尾随空格只可能通过首行规则命中 —— 与 pinned 上游行为一致。
  if (info === MERMAID_INFO_WORD) {
    return true;
  }
  const firstLine = String(content || "").trim().split(/\n/)[0].trim();
  return IMPLICIT_FIRST_LINES.indexOf(firstLine) >= 0 || IMPLICIT_GRAPH_LINE.test(firstLine);
}

function markdownItMermaidExport(md) {
  // 与 pinned 上游一样覆写 fence renderer；非 Mermaid fence 必须交回原 renderer。
  const originalFence = md.renderer.rules.fence;
  md.renderer.rules.fence = function (tokens, index, options, env, self) {
    const token = tokens[index];
    if (!isMermaidFence(token.info, token.content)) {
      return originalFence(tokens, index, options, env, self);
    }
    // features 只读这个语义标记（entry 在 render 之后调用 detectFeatures，见 entry.js 顺序）。
    token.meta = Object.assign({}, token.meta, { mr_mermaid: true });
    // 上游容器结构（含其 trim 语义）+ D2 escape。
    return '<div class="mermaid">' + md.utils.escapeHtml(String(token.content).trim()) + '</div>';
  };
}

module.exports = {
  markdownItMermaidExport: markdownItMermaidExport,
  isMermaidFence: isMermaidFence,
};
