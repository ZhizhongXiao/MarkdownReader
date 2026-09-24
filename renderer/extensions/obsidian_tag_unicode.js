"use strict";

/**
 * MarkdownReader compatibility extension：Obsidian tag 的 Unicode 识别。
 *
 * 背景：pinned vscode-office 的 src/service/markdown/ext/markdown-it-obsidian.js 里
 * isTagChar() 只接受 A-Z a-z 0-9 _ - /，因此 #笔记、#项目/子项、#abc中文 这类含 Unicode 的
 * tag 不会被识别。
 *
 * ownership 边界（本扩展只补上游缺失的那部分）：
 *   - 纯 ASCII candidate（#note、#project/sub、#a_b）→ 本扩展 return false，
 *     由紧随其后的 **upstream obsidian_tag rule** 消费：tag parser 仍归上游。
 *   - 含至少一个上游 ASCII 集之外的字符（Unicode \p{L}\p{N}\p{M}）→ 本扩展消费**整个**
 *     candidate（避免上游只吃掉 ASCII 前缀、把中文残留成普通文本），push 的仍是上游的 token
 *     类型 obsidian_tag，渲染继续由上游 renderer rule 完成。
 *
 * 不 fork 上游插件、不修改上游源码、不新增 lexical 边界：URL fragment（…/page#section）由更早的
 * linkify rule 消费，因此不会变成 tag；word#tag 的行为与上游保持一致。
 *
 * 依赖 pinned 上游的 obsidian_tag rule：若上游将来改名或移除，这里必须**明确失败**并要求
 * 重新审计 adapter，而不是悄悄退化成 MarkdownReader 自己接管 tag parser —— 这是 upstream
 * updateability contract 的一部分，因此注册不使用 try/catch fallback。
 *
 * 另注：markdown-it 14 的 Ruler.at(name, fn, options) 是「替换/启用」API，不传 fn 会把原规则
 * 清空；所以这里只用非破坏性的 ruler.before(...)。
 */

const TAG_SEPARATORS = /[_\-\/]/;
// pinned 上游的字符集：出现集合之外的字符才需要 MarkdownReader 兼容接管。
const UPSTREAM_TAG_CHARS = /[A-Za-z0-9_\-\/]/;

function isTagChar(ch) {
  if (!ch) {
    return false;
  }
  if (TAG_SEPARATORS.test(ch)) {
    return true;
  }
  return /[\p{L}\p{N}\p{M}]/u.test(ch);
}

/**
 * 从 source[start] 的 # 之后扫描整个 tag candidate（逐个 code point，避免截断代理对）。
 *
 * @returns {{ length: number, needsUnicodeCompat: boolean }}
 *   length：tag 正文长度（不含前导 #）；
 *   needsUnicodeCompat：candidate 中是否出现上游 ASCII 集之外的字符（决定是否由本扩展接管）。
 */
function scanTagCandidate(source, start) {
  let length = 0;
  let needsUnicodeCompat = false;

  for (const ch of source.slice(start + 1)) {
    if (!isTagChar(ch)) {
      break;
    }
    if (!UPSTREAM_TAG_CHARS.test(ch)) {
      needsUnicodeCompat = true;
    }
    length += ch.length;
  }

  return { length: length, needsUnicodeCompat: needsUnicodeCompat };
}

function markdownItObsidianTagUnicode(md) {
  const ruler = md.inline.ruler;

  const rule = function (state, silent) {
    const start = state.pos;
    if (state.src.charCodeAt(start) !== 0x23 /* # */) {
      return false;
    }

    const candidate = scanTagCandidate(state.src, start);
    if (candidate.length === 0) {
      return false;
    }
    // 纯 ASCII candidate 交给上游 obsidian_tag rule：这里不接管。
    if (!candidate.needsUnicodeCompat) {
      return false;
    }
    if (silent) {
      return true;
    }

    const token = state.push("obsidian_tag", "span", 0);
    token.content = state.src.slice(start, start + 1 + candidate.length);
    state.pos = start + 1 + candidate.length;
    return true;
  };

  // 明确依赖 pinned 上游的 obsidian_tag rule：缺失即抛错，不做静默 fallback。
  ruler.before("obsidian_tag", "mr_obsidian_tag", rule);
}

module.exports = {
  markdownItObsidianTagUnicode: markdownItObsidianTagUnicode,
  scanTagCandidate: scanTagCandidate,
};
