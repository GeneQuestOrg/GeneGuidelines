/**
 * Write the static pages into `dist/` after `vite build`.
 *
 * Each page reuses the built `index.html` verbatim — same hashed bundle, same
 * fonts, same analytics snippet — and only swaps the head tags that describe the
 * page and inserts the static body. The app then boots exactly as before: the
 * first thing `main.tsx` does is drop the static block, so a visitor with
 * JavaScript sees the real app and never a stale copy of it.
 *
 * The backend serves `<dir>/index.html` for a directory path (backend/main.py,
 * `spa_fallback`); without that these files would be written and never served.
 *
 * The home page is one of them, so `dist/index.html` stops being the shell every other route falls back to. The shell is written to `dist/_shell.html` first, and without a canonical link or og:url: the template's point at the home page, and served on /diseases/mas or /doctors they told a search engine that every such page was a duplicate of the home page. The app sets the right canonical itself once it runs (src/hooks/useDocumentMeta.ts).
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildPages } from "./pages.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const dist = join(root, "dist");

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** Drop the template's own page description so the page's own can replace it. */
function stripTemplateMeta(html) {
  return html
    .replace(/\s*<title>[\s\S]*?<\/title>/i, "")
    .replace(/\s*<meta\b[^>]*\bname="description"[^>]*>/gi, "")
    .replace(/\s*<meta\b[^>]*\bproperty="og:[^"]*"[^>]*>/gi, "")
    .replace(/\s*<meta\b[^>]*\bname="twitter:[^"]*"[^>]*>/gi, "")
    .replace(/\s*<link\b[^>]*\brel="canonical"[^>]*>/gi, "")
    .replace(/\s*<script type="application\/ld\+json">[\s\S]*?<\/script>/gi, "");
}

/**
 * Minimal styling for the static block. It is scoped to `#gg-prerender` and
 * inlined, because the app's stylesheet is written for the React markup and this
 * is a plain document. It stays readable, never hidden: text a crawler is shown
 * and a reader is not is the oldest bad idea in search.
 */
const STATIC_STYLE = `<style>
      #gg-prerender {
        max-width: 46rem;
        margin: 0 auto;
        padding: 2rem 1rem 4rem;
        font: 16px/1.6 ui-sans-serif, system-ui, sans-serif;
        color: #161614;
      }
      #gg-prerender h1 { font-size: 1.9rem; line-height: 1.2; }
      #gg-prerender h2 { font-size: 1.2rem; margin-top: 2rem; }
      #gg-prerender blockquote {
        margin: 0.35rem 0 0.9rem;
        padding-left: 0.9rem;
        border-left: 2px solid #D7D2C7;
        font-style: italic;
        color: #3A3835;
      }
      #gg-prerender .ggp-q { font-weight: 600; margin-bottom: 0.2rem; }
      #gg-prerender .ggp-note { font-size: 0.85rem; color: #6E6A60; }
      #gg-prerender .ggp-links { margin-top: 1.5rem; font-size: 0.9rem; }
      #gg-prerender .ggp-facts dt { font-weight: 600; display: inline; }
      #gg-prerender .ggp-facts dd { display: inline; margin: 0 1rem 0 0.3rem; }
      #gg-prerender ul, #gg-prerender ol { padding-left: 1.2rem; }
      #gg-prerender li { margin-bottom: 0.9rem; }
    </style>`;

function head(page) {
  const alternates = page.alternates
    .map(
      ({ hreflang, href }) =>
        `    <link rel="alternate" hreflang="${hreflang}" href="${esc(href)}" />`,
    )
    .join("\n");
  return [
    `    <title>${esc(page.title)}</title>`,
    `    <meta name="description" content="${esc(page.description)}" />`,
    `    <link rel="canonical" href="${esc(page.url)}" />`,
    alternates,
    `    <link rel="alternate" hreflang="x-default" href="${esc(
      page.alternates.find((alt) => alt.hreflang === "en").href,
    )}" />`,
    `    <meta property="og:type" content="article" />`,
    `    <meta property="og:site_name" content="GeneGuidelines" />`,
    `    <meta property="og:title" content="${esc(page.title)}" />`,
    `    <meta property="og:description" content="${esc(page.description)}" />`,
    `    <meta property="og:url" content="${esc(page.url)}" />`,
    `    <meta property="og:image" content="https://geneguidelines.genequest.org/logo.png" />`,
    `    <meta property="og:locale" content="${page.locale}" />`,
    `    <meta name="twitter:card" content="summary" />`,
    `    <meta name="twitter:title" content="${esc(page.title)}" />`,
    `    <meta name="twitter:description" content="${esc(page.description)}" />`,
    `    <meta name="twitter:image" content="https://geneguidelines.genequest.org/logo.png" />`,
    `    <script type="application/ld+json">${JSON.stringify(page.jsonLd)}</script>`,
    `    ${STATIC_STYLE}`,
  ].join("\n");
}

function render(template, page) {
  const html = stripTemplateMeta(template)
    .replace(/<html\b[^>]*lang="[^"]*"/i, `<html lang="${page.locale}"`)
    .replace("</head>", `${head(page)}\n  </head>`)
    .replace(
      '<div id="root"></div>',
      `<div id="gg-prerender">\n${page.body}\n</div>\n    <div id="root"></div>`,
    );
  if (!html.includes('id="gg-prerender"')) {
    throw new Error("prerender: could not find the app root in dist/index.html");
  }
  return html;
}

/** The fallback shell: the template minus the tags that name one URL as the page. */
function shell(template) {
  return template
    .replace(/\s*<link\b[^>]*\brel="canonical"[^>]*>/gi, "")
    .replace(/\s*<meta\b[^>]*\bproperty="og:url"[^>]*>/gi, "");
}

function main() {
  const templatePath = join(dist, "index.html");
  let template;
  try {
    template = readFileSync(templatePath, "utf8");
  } catch {
    throw new Error(`prerender: ${templatePath} not found — run vite build first`);
  }

  writeFileSync(join(dist, "_shell.html"), shell(template), "utf8");
  console.log("prerender: fallback shell → /dist/_shell.html");

  const pages = buildPages();
  for (const page of pages) {
    const target = join(dist, page.path.replace(/^\//, ""), "index.html");
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, render(template, page), "utf8");
    console.log(`prerender: ${page.path} → ${target.slice(root.length)}`);
  }
  console.log(`prerender: wrote ${pages.length} pages`);
}

main();
