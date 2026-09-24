"use strict";

/**
 * MarkdownReader compatibility extension：Obsidian tag 的 Unicode 识别。
 *
 * 背景：pinned vscode-office 的 src/service/markdown/ext/markdown-it-obsidian.js 里
 * isTagChar() 只接受 ASCII 字母/数字与 _ - /，因此 #笔记、#项目/子项 不会被识别成 tag。
 * Phase 1 的 TARGET fixture 正是中文 tag，所以这里做**最小**扩展：
 *
 *   1. 放宽字符集：在 ASCII 之外接受 Unicode 字母/数字/组合记号（\p{L}\p{N}\p{M}）；
 *   2. 不新增 lexical 边界：沿用上游的「# 后必须紧跟 tag 字符」规则，只放宽字符集。
 *      URL 里的 fragment（…/page#section）由更早的 linkify rule 消费，因此不会变成 tag。
 *
 * 不 fork 上游插件、不修改上游源码、不新建第二套 tag grammar：本扩展注册的 rule 名是
 * mr_obsidian_tag，插在上游 obsidian_tag 之前；它 push 的仍是**上游的 token 类型**
 * obsidian_tag（content 含前导 #，与上游一致），渲染继续由上游的 renderer rule 完成。
 *
 * 注意：markdown-it 14 的 Ruler.at(name, fn, options) 是「替换/启用」API —— 它会直接把
 * fn 写进规则，未传 fn 就会把原规则清空。所以这里不做 at() 探测，只做非破坏性插入。
 */

const TAG_SEPARATORS = /[_\-\/]/;

function isTagChar(ch) {
  if (!ch) {
    return false;
  }
  if (TAG_SEPARATORS.test(ch)) {
    return true;
  }
  return /[\p{L}\p{N}\p{M}]/u.test(ch);
}

// 逐个 code point 前进，避免在代理对被拆开时截断 tag。
function tagLength(source, start) {
  let length = 0;
  for (const ch of source.slice(start + 1)) {
    if (!isTagChar(ch)) {
      break;
    }
    length += ch.length;
  }
  return length;
}

function markdownItObsidianTagUnicode(md) {
  const ruler = md.inline.ruler;

  const rule = function (state, silent) {
    const start = state.pos;
    if (state.src.charCodeAt(start) !== 0x23 /* # */) {
      return false;
    }
    const length = tagLength(state.src, start);
    if (length === 0) {
      return false;
    }
    if (silent) {
      return true;
    }

    const token = state.push("obsidian_tag", "span", 0);
    token.content = state.src.slice(start, start + 1 + length);
    state.pos = start + 1 + length;
    return true;
  };

  // 先插到上游 obsidian_tag 之前；上游规则不存在时退回到 emphasis 之前。
  try {
    ruler.before("obsidian_tag", "mr_obsidian_tag", rule);
  } catch (error) {
    ruler.before("emphasis", "mr_obsidian_tag", rule);
  }
}

module.exports = { markdownItObsidianTagUnicode: markdownItObsidianTagUnicode };
