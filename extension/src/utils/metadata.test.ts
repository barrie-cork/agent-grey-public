/**
 * Self-check for extractMetadata. No framework - run with:
 *   cd extension && npx tsx src/utils/metadata.test.ts
 *
 * Feeds a minimal fake Document and asserts the priority chain.
 */
import assert from "node:assert/strict";

import { extractMetadata } from "./metadata";

function fakeDoc(opts: {
  metas?: Record<string, string>;
  jsonld?: unknown;
  canonical?: string;
  title?: string;
}): Document {
  const metaEls = Object.entries(opts.metas ?? {}).map(([key, content]) => ({
    getAttribute(attr: string): string | null {
      if (attr === "name" || attr === "property") return key;
      if (attr === "content") return content;
      return null;
    },
  }));
  const scriptEls = opts.jsonld
    ? [{ textContent: JSON.stringify(opts.jsonld) }]
    : [];
  const linkEl = opts.canonical ? { href: opts.canonical } : null;

  return {
    title: opts.title ?? "",
    location: { href: "https://example.test/page" },
    querySelectorAll(sel: string): unknown[] {
      if (sel === "meta") return metaEls;
      if (sel.includes("ld+json")) return scriptEls;
      return [];
    },
    querySelector(sel: string): unknown {
      if (sel.includes("canonical")) return linkEl;
      return null;
    },
  } as unknown as Document;
}

// 1. citation_* wins over og:/author
{
  const md = extractMetadata(
    fakeDoc({
      metas: {
        citation_author: "Ada Lovelace",
        author: "Someone Else",
        "og:title": "OG Title",
        citation_title: "Citation Title",
      },
    }),
  );
  assert.equal(md.author, "Ada Lovelace");
  assert.equal(md.title, "Citation Title");
}

// 2. JSON-LD used only when meta tags absent
{
  const md = extractMetadata(
    fakeDoc({
      jsonld: {
        name: "LD Title",
        author: { name: "LD Author" },
        datePublished: "2021-03-04T10:00:00Z",
        publisher: { name: "LD Press" },
      },
    }),
  );
  assert.equal(md.title, "LD Title");
  assert.equal(md.author, "LD Author");
  assert.equal(md.publisher, "LD Press");
  assert.equal(md.published_date, "2021-03-04");
}

// 3. <title> fallback when nothing else present
{
  const md = extractMetadata(fakeDoc({ title: "Bare Title" }));
  assert.equal(md.title, "Bare Title");
  assert.equal(md.author, "");
  assert.equal(md.published_date, "");
}

// 4. published_date normalised from an ISO datetime meta
{
  const md = extractMetadata(
    fakeDoc({ metas: { "article:published_time": "2020-12-31T23:59:00+00:00" } }),
  );
  assert.equal(md.published_date, "2020-12-31");
}

// 5. slash-separated citation_publication_date normalised to dashes
{
  const md = extractMetadata(
    fakeDoc({ metas: { citation_publication_date: "2021/03/29" } }),
  );
  assert.equal(md.published_date, "2021-03-29");
}

// 6. human-readable date from JSON-LD normalised via Date fallback
{
  const md = extractMetadata(
    fakeDoc({
      jsonld: { datePublished: "29 April 2020", name: "Test" },
    }),
  );
  assert.equal(md.published_date, "2020-04-29");
}

// 7. canonical <link> preferred over og:url / location
{
  const md = extractMetadata(
    fakeDoc({
      canonical: "https://canonical.test/x",
      metas: { "og:url": "https://og.test/y" },
    }),
  );
  assert.equal(md.canonical_url, "https://canonical.test/x");
}

console.log("metadata.test.ts: all assertions passed");
