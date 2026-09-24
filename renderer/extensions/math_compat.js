"use strict";

/**
 * MarkdownReader compatibility extension：upstream 缺失的数学分隔符。
 *
 * ownership：
 *   $…$ / $$…$$             → pinned upstream KaTeX plugin（本文件完全不碰）
 *   \(…\)  \[…\]  begin/end  → 本扩展解析，并 push **上游 token 类型**
 *                              math_inline / math_block，渲染由 upstream 的 KaTeX renderer
 *                              rule 完成（与 dollar 路径同类 markup，无 renderer 冲突）。
 *
 * 为什么不复用 markdown-it-texmath：它按硬编码规则名注册，并覆盖
 * renderer.rules.math_inline / math_block —— 与 upstream 的规则名和渲染键完全重合，只加
 * “缺失 delimiter”会连带接管 dollar 渲染（ownership 反转）。审计记录见 Phase 4B 报告。
 *
 * grammar 与旧 production renderer characterization 一致：
 *   - inline \(…\)：单行，内部允许转义对；跨行/未闭合不成立
 *   - block \[…\]：必须行首、可多行；段中不生效（注册时不带 alt，与旧行为一致）
 *   - begin/end：env 名为小写字母，\end 必须与 \begin 同名，content 含 begin/end 本体
 *   - 4 空格缩进属于代码块，不在这里处理
 *
 * 说明：本文件刻意不含反斜杠字面量，改用 String.fromCharCode(92) 构造分隔符，避免多层转义
 * 出错（Phase 4A 的教训）。
 */

const BACKSLASH = String.fromCharCode(92);
const BACKSLASH_CODE = 92;
const NEWLINE = 10;

const INLINE_OPEN = BACKSLASH + "(";
const INLINE_CLOSE = BACKSLASH + ")";
const BLOCK_OPEN = BACKSLASH + "[";
const BLOCK_CLOSE = BACKSLASH + "]";
const ENV_BEGIN_PREFIX = BACKSLASH + "begin{";
const ENV_END_PREFIX = BACKSLASH + "end{";

// \( … \)
function readBracketInline(source, start) {
  if (source.slice(start, start + INLINE_OPEN.length) !== INLINE_OPEN) {
    return null;
  }
  let position = start + INLINE_OPEN.length;
  while (position < source.length) {
    const code = source.charCodeAt(position);
    if (code === NEWLINE) {
      return null;
    }
    if (code === BACKSLASH_CODE) {
      if (source.slice(position, position + INLINE_CLOSE.length) === INLINE_CLOSE) {
        return {
          content: source.slice(start + INLINE_OPEN.length, position),
          end: position + INLINE_CLOSE.length,
        };
      }
      position += 2; // 跳过转义对
      continue;
    }
    position += 1;
  }
  return null;
}

// \[ … \]
function readBracketBlock(source, start) {
  if (source.slice(start, start + BLOCK_OPEN.length) !== BLOCK_OPEN) {
    return null;
  }
  let position = start + BLOCK_OPEN.length;
  while (position < source.length) {
    const isClose = source.charCodeAt(position) === BACKSLASH_CODE &&
      source.slice(position, position + BLOCK_CLOSE.length) === BLOCK_CLOSE;
    if (isClose) {
      return {
        content: source.slice(start + BLOCK_OPEN.length, position),
        end: position + BLOCK_CLOSE.length,
      };
    }
    position += 1;
  }
  return null;
}

// \begin{env} … \end{env}
function readEnvironment(source, start) {
  if (source.slice(start, start + ENV_BEGIN_PREFIX.length) !== ENV_BEGIN_PREFIX) {
    return null;
  }
  const nameEnd = source.indexOf("}", start + ENV_BEGIN_PREFIX.length);
  if (nameEnd < 0) {
    return null;
  }
  const environment = source.slice(start + ENV_BEGIN_PREFIX.length, nameEnd);
  if (!/^[a-z]+$/.test(environment)) {
    return null;
  }
  const endMarker = ENV_END_PREFIX + environment + "}";
  const end = source.indexOf(endMarker, nameEnd + 1);
  if (end < 0) {
    return null;
  }
  return { content: source.slice(start, end + endMarker.length), end: end + endMarker.length };
}

function countNewlines(text) {
  let count = 0;
  for (let index = 0; index < text.length; index += 1) {
    if (text.charCodeAt(index) === NEWLINE) {
      count += 1;
    }
  }
  return count;
}

function markdownItMathCompat(md) {
  md.inline.ruler.before("escape", "mr_math_bracket_inline", function (state, silent) {
    const parsed = readBracketInline(state.src, state.pos);
    if (!parsed) {
      return false;
    }
    if (silent) {
      return true;
    }
    const token = state.push("math_inline", "math", 0);
    token.markup = INLINE_OPEN;
    token.content = parsed.content;
    state.pos = parsed.end;
    return true;
  });

  const blockRule = function (reader, markup) {
    return function (state, startLine, endLine, silent) {
      if (state.sCount[startLine] - state.blkIndent >= 4) {
        return false;
      }
      const start = state.bMarks[startLine] + state.tShift[startLine];
      const parsed = reader(state.src, start);
      if (!parsed) {
        return false;
      }
      const nextLine = startLine + countNewlines(state.src.slice(start, parsed.end)) + 1;
      if (nextLine > endLine) {
        return false;
      }
      if (silent) {
        return true;
      }
      const token = state.push("math_block", "math", 0);
      token.block = true;
      token.markup = markup;
      token.content = parsed.content;
      token.map = [startLine, nextLine];
      state.line = nextLine;
      return true;
    };
  };

  md.block.ruler.before("fence", "mr_math_bracket_block", blockRule(readBracketBlock, BLOCK_OPEN));
  md.block.ruler.before("fence", "mr_math_env_block", blockRule(readEnvironment, ENV_BEGIN_PREFIX));
}

module.exports = { markdownItMathCompat: markdownItMathCompat };
