---
name: calibre-analyze-book-structure
description: Analyze the logical, physical, navigation, and semantic structure of books in Calibre or supplied EPUB/XHTML/PDF files. Use alongside the calibre-mcp tools when the user asks for a chapter/part hierarchy, front-matter/body/back-matter map, heading-level audit, TOC-versus-content comparison, EPUB spine/nav analysis, chapter boundary diagnosis, structural anomaly report, or a plan for extracting sections with XPath. Trigger on book structure, content structure, chapter map, outline audit, TOC mismatch, spine order, EPUB navigation, heading hierarchy, or structural analysis.
---

# Calibre book structure analysis

Build an evidence-backed structure map without reading or reproducing the whole book. Prefer the
`calibre_*` MCP tools; inspect raw EPUB files only when package-level evidence is necessary and the
file is in scope.

## Workflow

1. Resolve the book with `mcp__calibre__calibre_search` and confirm its ID with `mcp__calibre__calibre_get_book`.
2. Call `mcp__calibre__calibre_get_content` with `structure: true` before requesting prose. Treat its headings and
   cursors as the logical outline exposed by the server, not as proof of EPUB spine or TOC structure.
3. Sample content at the start, at suspected part/chapter boundaries, and near the end. Use small
   cursor-bounded reads. Do not walk the entire book unless the user explicitly needs exhaustive
   coverage.
4. When figures matter, call `mcp__calibre__calibre_get_figures` without indexes to inventory them; fetch only the
   few images needed to understand structural roles such as plates, diagrams, or appendices.
5. If semantic distribution matters, run `mcp__calibre__calibre_semantic_search` with `scope: book` for each major
   theme. Report where themes concentrate; do not infer absence from one failed query.
6. Reconcile the available layers and mark every conclusion as observed, inferred, or unavailable.

## Keep the layers separate

- **Logical:** parts, chapters, sections, appendices, notes, bibliography, index.
- **Physical:** PDF pages or EPUB content documents and their order.
- **Navigation:** EPUB nav/NCX entries, landmarks, page list, or PDF bookmarks.
- **Semantic:** where arguments, topics, examples, and evidence are distributed.

Do not claim that headings equal TOC entries or that MCP cursors equal EPUB file boundaries. If the
user needs exact package structure, inspect an exported EPUB copy and its OPF/nav/NCX files.

## Raw EPUB inspection

Use read-only extraction into a fresh temporary directory:

```powershell
calibre-debug -x "book.epub" "C:\tmp\book-exploded"
```

Inspect `META-INF/container.xml`, the referenced OPF, its manifest/spine, the EPUB 3 nav document,
and any EPUB 2 NCX. Never modify the source archive merely to analyze it. Use
`$calibre-write-xpath` when selectors are required.

## Analysis checks

Read [references/structure-analysis.md](references/structure-analysis.md) when producing a formal
report or comparing MCP structure with an EPUB package. At minimum check:

- missing, duplicated, or out-of-order headings;
- skipped heading levels and part/chapter ambiguity;
- front/back matter incorrectly mixed into the main narrative;
- nav entries whose targets are missing or whose labels disagree with body headings;
- spine items absent from navigation and navigation targets absent from the spine;
- unusually long or short sections that may indicate failed splitting or extraction;
- appendices, footnotes, endnotes, figures, or tables detached from their references.

## Output contract

Return:

1. a compact hierarchy tree;
2. a layer summary covering logical, physical, navigation, and semantic evidence;
3. an anomaly table with severity, evidence, and confidence;
4. extraction anchors: book ID/cursor, page, file plus fragment ID, or an XPath handoff;
5. explicit limitations and the next best verification step.

Paraphrase content. Do not emit long passages or reconstruct a copyrighted book.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
