"use strict";

// The one-shot and server entrypoints share this exact per-request pipeline.
const { okEnvelope } = require("./protocol");
const { createRenderer } = require("./upstream/create_renderer");
const { collectHeadings, headingAnchorFallback } = require("./document/headings");
const { detectFeatures } = require("./document/features");
const { transformDocumentLinks } = require("./document/links");
const { collectAuthorReferences } = require("./document/author_references");
const { collectResources } = require("./resources/collector");
const { resetKatexStyleCache } = require("./resources/katex_assets");
const { resetMermaidRuntimeCache } = require("./resources/mermaid_runtime");

async function renderRequest(request) {
  const warnings = [];
  const renderer = createRenderer({ options: request.options });
  renderer.md.use(headingAnchorFallback);
  if (!renderer.mathEnabled) {
    warnings.push("options.math=false：公式不会被渲染。");
  }
  const env = {};
  const tokens = renderer.md.parse(request.markdown, env);
  // Preserve the existing parse -> links -> provenance -> resources -> render order.
  const documentLinks = transformDocumentLinks(tokens, request.context);
  const authorReferences = collectAuthorReferences(tokens);
  const resources = await collectResources(tokens, request.context, request.options);
  const headings = collectHeadings(renderer.md, tokens, env);
  const html = renderer.md.renderer.render(tokens, renderer.md.options, env);
  return {
    html: html,
    headings: headings,
    features: detectFeatures(html, tokens),
    warnings: warnings.concat(documentLinks.warnings, resources.warnings),
    resources: {
      items: resources.items,
      styles: resources.styles,
      scripts: resources.scripts,
      author_references: authorReferences,
    },
  };
}

async function renderEnvelope(request) {
  // Module loading is shared, but resource failures/changes must behave like one-shot.
  // G1 smoke and the actual document still share caches within this single request.
  resetKatexStyleCache();
  resetMermaidRuntimeCache();
  const runtimeValidation = request.runtime_validation
    ? okEnvelope(await renderRequest(request.runtime_validation))
    : null;
  const envelope = okEnvelope(await renderRequest(request));
  if (runtimeValidation) {
    envelope.runtime_validation = runtimeValidation;
  }
  return envelope;
}

module.exports = { renderEnvelope };
