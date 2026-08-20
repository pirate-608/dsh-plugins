# Structure analysis reference

## Evidence model

| Layer | Primary evidence | Typical failure |
|---|---|---|
| Logical | `mcp__calibre__calibre_get_content structure:true`, sampled headings | false headings, skipped levels, duplicate titles |
| Physical | PDF pages; OPF manifest and spine | bad order, non-linear items, oversized content file |
| Navigation | EPUB nav/NCX; PDF bookmarks | broken target, stale label, missing landmark |
| Semantic | scoped semantic/full-text searches plus sampled passages | topic drift, unsupported absence claim |

Use these confidence labels:

- **Observed:** directly returned by a tool or parsed from the package.
- **Corroborated:** the same relation appears in two independent layers.
- **Inferred:** plausible from samples but not directly encoded.
- **Unavailable:** the current format/tool cannot expose it.

## Recommended report schema

```text
Book identity and formats
Hierarchy tree
Layer comparison
Section distribution
Structural anomalies
Extraction anchors
Limitations and next checks
```

For each anomaly record:

```text
severity: info | warning | error
layer: logical | physical | navigation | semantic
location: cursor, page, file#fragment, or XPath
evidence: short factual observation
impact: what the reader/converter loses
confidence: observed | corroborated | inferred
```

## EPUB reconciliation

1. Read `META-INF/container.xml` and locate the package document.
2. Map manifest IDs to hrefs and media types.
3. Read spine `itemref/@idref` order; note `linear="no"` items separately.
4. Locate the EPUB 3 nav item through `properties="nav"`; otherwise locate the NCX through the
   spine `toc` ID or the NCX media type.
5. Resolve every nav/NCX href relative to its document, including fragments.
6. Compare targets to the spine and then compare labels to target headings.
7. Inspect landmarks, page list, guide, notes, and appendices separately from the main TOC.

## Format-specific cautions

- A PDF bookmark tree is navigation metadata, not a reliable heading hierarchy.
- OCR output can invent headings or merge columns; report extraction quality before analyzing it.
- EPUB spine order is reading order, but `linear="no"` content may be auxiliary.
- One XHTML file can contain many chapters, and one chapter can span multiple files.
- CSS classes such as `chapter` are hints, not semantics; confirm with text and neighbors.
- Heading level skips can be intentional when styling markup is used poorly. Report impact rather
  than asserting authorial intent.

## Sampling strategy

Use the smallest sample that can falsify the current hypothesis:

- first content item: title/front matter boundary;
- one boundary from each part;
- one normal chapter boundary;
- first appendix/notes/bibliography boundary;
- final content item;
- every location implicated by an anomaly.

Escalate to exhaustive traversal only when the requested deliverable requires complete counts.
