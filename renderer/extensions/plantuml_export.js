"use strict";

/**
 * MarkdownReader PlantUML export adaptation（Phase 4C）。
 *
 * 语义来源：
 *   pinned vscode-office 908258dafc827ce0475fe7671d414914fbd3867b
 *   src/service/markdown/markdown-pdf.js → .use(markdownItPlantuml)（上游依赖 ^1.4.1）
 *
 * 本扩展只做三件事：
 *   1) 注册 markdown-it-plantuml：uml_diagram token 与 <img> 渲染都归插件；
 *   2) 把 URL 构造集中到一个实现 plantumlEncodedUrl（唯一公式），并通过插件的 generateSource
 *      选项交给它使用（plantumlImageSource 只按插件默认公式包 @start…/@end…）；server 只有
 *      一个来源；
 *   3) 附加围栏形式 ```plantuml / ```puml：把 fence token 换成同一个 uml_diagram token。
 *      pinned 上游的**导出**路径只有裸 @startuml 块（vditor 编辑器的围栏支持不属于导出语义），
 *      而迁移语料 target/plantuml.md 用的是围栏形式 —— 这是 Phase 4C 的 adapter 附加，
 *      登记在 docs/MARKDOWN_COMPATIBILITY.md 的 G7 行。
 *
 * 不做任何网络访问：这里只生成 server URL（AGENTS §10；抓图与内嵌属 Phase 5）。
 */

const markdownItPlantuml = require("markdown-it-plantuml");
const deflate = require("markdown-it-plantuml/lib/deflate");

const DEFAULT_PLANTUML_SERVER = "https://www.plantuml.com/plantuml";
const DEFAULT_DIAGRAM_NAME = "uml";
const DEFAULT_IMAGE_FORMAT = "svg";
const FENCE_LANGUAGES = ["plantuml", "puml"];
const FENCE_FALLBACK_ALT = "uml diagram";

// 唯一的 URL 构造实现：插件默认公式 = DEFLATE(level 9) + encode64。
function plantumlEncodedUrl(source, pluginOptions) {
  const options = pluginOptions || {};
  const server = options.server || DEFAULT_PLANTUML_SERVER;
  const imageFormat = options.imageFormat || DEFAULT_IMAGE_FORMAT;
  const compressed = deflate.encode64(deflate.zip_deflate(unescape(encodeURIComponent(source)), 9));
  return server + "/" + imageFormat + "/" + compressed;
}

// 插件的 generateSource 选项：裸 @startuml 块由插件传入「标记之间的内容」，
// 这里按插件默认公式重新包上 @start…/@end…。
function plantumlImageSource(umlCode, pluginOptions) {
  const options = pluginOptions || {};
  const diagramName = options.diagramName || DEFAULT_DIAGRAM_NAME;
  const payload = "@start" + diagramName + "\n" + umlCode + "\n@end" + diagramName;
  return plantumlEncodedUrl(payload, options);
}

function fenceWords(info) {
  const trimmed = String(info || "").trim();
  if (!trimmed) {
    return { language: "", params: "" };
  }
  const match = trimmed.match(/^(\S+)([\s\S]*)$/);
  return { language: match[1], params: match[2] };
}

// 契约边界（不要在这里扩大 grammar）：
//   plantuml / puml fence → MarkdownReader adapter extension
//   body 是完整 PlantUML source
//   不定义缺失 @startuml/@enduml 时自动补齐
// 未来若要支持「省略标记」的写法，应作为独立产品能力：带自己的 fixture 与 contract。
function diagramTokenForFence(state, token, pluginOptions) {
  const words = fenceWords(token.info);
  if (FENCE_LANGUAGES.indexOf(words.language) < 0) {
    return null;
  }
  // 围栏形式的 body 就是作者写的完整 PlantUML 源（通常自带 @startuml/@enduml）：原样送去编码，
  // 不删标记、也不重新包装，避免改写作者的图源。
  const source = String(token.content || "").replace(/\n$/, "");
  // 与插件对 @startuml <params> 的语义一致：参数首个空格之后是 alt。
  const alt = words.params ? words.params.slice(1) : FENCE_FALLBACK_ALT;
  const diagram = new state.Token("uml_diagram", "img", 0);
  diagram.attrs = [["src", plantumlEncodedUrl(source, pluginOptions)], ["alt", ""]];
  diagram.block = true;
  diagram.children = [];
  state.md.inline.parse(alt, state.md, state.env, diagram.children);
  diagram.info = words.params;
  diagram.map = token.map;
  diagram.markup = "```" + words.language;
  return diagram;
}

function markdownItPlantumlExport(md, pluginOptions) {
  const options = {
    server: (pluginOptions && pluginOptions.server) || DEFAULT_PLANTUML_SERVER,
    generateSource: plantumlImageSource,
  };
  md.use(markdownItPlantuml, options);

  // 围栏形式：parse 之后、render 之前把 fence token 换成插件的 uml_diagram token，
  // 这样 feature 判断与 <img> 渲染都仍然只有 plugin 语义一个来源。
  md.core.ruler.push("mr_plantuml_fence", function (state) {
    const tokens = state.tokens;
    for (let index = 0; index < tokens.length; index += 1) {
      if (tokens[index].type !== "fence") {
        continue;
      }
      const diagram = diagramTokenForFence(state, tokens[index], options);
      if (diagram) {
        tokens[index] = diagram;
      }
    }
  });
}

module.exports = {
  markdownItPlantumlExport: markdownItPlantumlExport,
  plantumlEncodedUrl: plantumlEncodedUrl,
  plantumlImageSource: plantumlImageSource,
  DEFAULT_PLANTUML_SERVER: DEFAULT_PLANTUML_SERVER,
  FENCE_LANGUAGES: FENCE_LANGUAGES,
};
