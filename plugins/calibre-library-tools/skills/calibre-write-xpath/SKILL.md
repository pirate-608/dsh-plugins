---
name: calibre-write-xpath
description: Write, explain, and validate XPath expressions for Calibre conversion and ebook internals, including XHTML chapter detection, page-break and TOC rules, EPUB OPF manifest/spine queries, EPUB 3 nav documents, EPUB 2 NCX, SVG, and MathML. Use when the user asks for XPath, chapter selectors, level1/2/3 TOC expressions, start-reading selectors, namespace-safe EPUB queries, Calibre ebook-convert structure detection, selector debugging, or an explanation of why an XPath matches zero or too many nodes.
---

# Calibre EPUB XPath

Author XPath against the actual document and target engine. For Calibre conversion, assume XPath
1.0 plus Calibre/lxml extensions such as `re:test()`. Internally Calibre represents content as
XHTML, so use the `h:` prefix for XHTML elements.

## Workflow

1. Establish the target: `--chapter`, `--page-breaks-before`, `--start-reading-at`,
   `--level1-toc`, `--level2-toc`, `--level3-toc`, or a raw OPF/nav/NCX query.
2. Inspect a representative XML/XHTML file. Record its root element, namespace declarations,
   heading/class/id patterns, and at least one positive and negative example.
3. Start with the narrowest structural selector, then add predicates. Avoid matching by visible text
   when stable elements or class tokens exist.
4. Validate on every representative file with `scripts/validate_xpath.py` under `calibre-debug`.
5. For Calibre structure options, require a node-set of elements. Report match count and show short
   labels/paths before recommending the expression.
6. Test the final conversion on a copy with `ebook-convert ... --debug-pipeline <dir>` when the
   selector affects splitting or TOC generation.

## Validation command

```powershell
calibre-debug -e "<skill-dir>\scripts\validate_xpath.py" -- `
  --file "chapter.xhtml" `
  --xpath "//h:h1 | //h:h2" `
  --require-elements
```

For package metadata:

```powershell
calibre-debug -e "<skill-dir>\scripts\validate_xpath.py" -- `
  --file "content.opf" `
  --xpath "//opf:spine/opf:itemref/@idref"
```

The validator predefines `h`, `epub`, `opf`, `dc`, `ncx`, `re`, `svg`, and `m` namespaces. Add a
custom mapping with repeated `--ns prefix=URI` arguments.

## Hard rules

- Do not use unprefixed `//h1` against namespaced XHTML; it normally matches nothing.
- Match class tokens with
  `contains(concat(' ', normalize-space(@class), ' '), ' chapter ')`, not `contains(@class,
  'chapter')` when false positives matter.
- Stay within XPath 1.0 for portable Calibre expressions. Do not emit XPath 2.0/3.1 functions such
  as `matches()`, `lower-case()`, `ends-with()`, or `tokenize()`.
- Use Calibre's `re:test(., 'pattern', 'i')` for regex/case-insensitive text matching.
- Attribute nodes are not elements. Expressions supplied to Calibre chapter/TOC detection must
  select elements, while diagnostic OPF queries may intentionally return attributes or strings.
- Use `/` to disable Calibre chapter or page-break detection only when that is the user's intent.
- Quote shell arguments separately from XPath string literals; validate the exact expression that
  will be passed to `ebook-convert`.

## Recipes

Read [references/xpath-recipes.md](references/xpath-recipes.md) for namespace mappings, Calibre
option examples, OPF/nav/NCX selectors, and failure diagnostics. Adapt recipes to observed markup;
never recommend a selector solely because it looks conventional.

## Output contract

Return the XPath in a code block, its target option/engine, namespace assumptions, representative
matches and non-matches, validation evidence, and a safer fallback if markup varies across files.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
