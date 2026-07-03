/**
 * In-browser page metadata extraction (Phase 2, shaping decision #5).
 *
 * `extractMetadata` is injected into the page via chrome.scripting.executeScript,
 * so it must be FULLY self-contained: no imports, no references to module-scope
 * helpers. Everything it needs lives inside the function body.
 *
 * Priority chain: Highwire citation_* > Dublin Core > Open Graph/article >
 * JSON-LD > <title> fallback.
 */

export interface PageMetadata {
  title: string;
  author: string;
  published_date: string;
  publisher: string;
  document_type: string;
  site_name: string;
  canonical_url: string;
}

export function extractMetadata(doc: Document = document): PageMetadata {
  // Collect all meta tags keyed by lowercased name/property (first wins).
  const metas: Record<string, string> = {};
  for (const m of Array.from(doc.querySelectorAll("meta"))) {
    const key = (
      m.getAttribute("name") ||
      m.getAttribute("property") ||
      ""
    ).toLowerCase();
    const content = (m.getAttribute("content") || "").trim();
    if (key && content && !(key in metas)) metas[key] = content;
  }

  // First JSON-LD object carrying useful fields.
  let ld: Record<string, unknown> = {};
  for (const s of Array.from(
    doc.querySelectorAll('script[type="application/ld+json"]'),
  )) {
    try {
      const parsed = JSON.parse(s.textContent || "{}");
      // @graph may be an array, a single object, or absent
      const graph = parsed && typeof parsed === "object" ? parsed["@graph"] : undefined;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const objs: any[] = Array.isArray(parsed)
        ? parsed
        : Array.isArray(graph)
          ? graph
          : graph
            ? [graph]
            : [parsed];
      const hit = objs.find(
        (o) => o && (o.name || o.headline || o.author || o.datePublished),
      );
      if (hit) {
        ld = hit;
        break;
      }
    } catch {
      // malformed JSON-LD - ignore
    }
  }

  // Resolve a JSON-LD value that may be a string, {name}, or array of those.
  const ldName = (o: unknown): string => {
    if (!o) return "";
    if (typeof o === "string") return o;
    if (Array.isArray(o)) return ldName(o[0]);
    return (o as { name?: string }).name || "";
  };

  // First non-empty value.
  const pick = (...vals: string[]): string => {
    for (const v of vals) if (v && v.trim()) return v.trim();
    return "";
  };

  // Normalise to YYYY-MM-DD when possible (Django parse_date is date-only).
  // ponytail: handles slashes (citation_publication_date "2021/03/29") and
  // human-readable ("29 April 2020") via Date fallback. Returns "" on junk.
  const normDate = (v: string): string => {
    if (!v) return "";
    const s = v.replace(/\//g, "-");
    const m = s.match(/\d{4}-\d{2}-\d{2}/);
    if (m) return m[0];
    const d = new Date(v);
    if (!isNaN(d.getTime())) {
      const y = d.getFullYear();
      const mo = String(d.getMonth() + 1).padStart(2, "0");
      const da = String(d.getDate()).padStart(2, "0");
      return `${y}-${mo}-${da}`;
    }
    return "";
  };

  const datePublished =
    typeof ld.datePublished === "string" ? ld.datePublished : "";

  const publisher = pick(
    metas["citation_publisher"],
    metas["dc.publisher"],
    metas["dcterms.publisher"],
    ldName(ld.publisher),
    metas["og:site_name"],
  );

  const canonicalLink = doc.querySelector(
    'link[rel="canonical"]',
  ) as HTMLLinkElement | null;

  return {
    title: pick(
      metas["citation_title"],
      metas["dc.title"],
      metas["og:title"],
      ldName(ld.name) || ldName(ld.headline),
      doc.title,
    ),
    author: pick(
      metas["citation_author"],
      metas["dc.creator"],
      metas["author"],
      metas["article:author"],
      ldName(ld.author),
    ),
    published_date: normDate(
      pick(
        metas["citation_publication_date"],
        metas["citation_date"],
        metas["dc.date"],
        metas["dcterms.issued"],
        metas["dcterms.date"],
        metas["article:published_time"],
        metas["og:article:published_time"],
        datePublished,
      ),
    ),
    publisher,
    document_type: pick(metas["og:type"]),
    site_name: pick(metas["og:site_name"], publisher),
    canonical_url: pick(
      canonicalLink ? canonicalLink.href : "",
      metas["og:url"],
      doc.location ? doc.location.href : "",
    ),
  };
}
