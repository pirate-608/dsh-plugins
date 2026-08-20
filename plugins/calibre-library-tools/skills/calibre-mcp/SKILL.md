---
name: calibre-mcp
description: Search, read, and safely curate a Calibre ebook library through the calibre-mcp server. Use for finding books, metadata/full-text/semantic search, reading excerpts or chapter maps, listing figures and categories, auditing metadata quality, finding duplicates, building search indexes, or previewing gated library maintenance. Trigger on Calibre, ebook library, find a book, search inside a book, read a chapter, book metadata, duplicates, library cleanup, or semantic book search.
---

# Calibre MCP operations

Prefer the `calibre_*` MCP tools. This plugin connects to `http://localhost:8080` and exposes write
tools because the user explicitly enabled them. Keep every mutation preview-first and narrowly scoped.

## Hard rules

- Discover libraries with `mcp__calibre__calibre_list_libraries`; never assume names, IDs, or paths.
- Start with `mcp__calibre__calibre_ping` when connectivity is uncertain.
- Use metadata search for known fields, full-text search for exact wording, and semantic search for
  concepts. If semantic search is unavailable or incomplete, build a scoped index first.
- Call `mcp__calibre__calibre_get_content` with `structure: true` before walking a long book. Read bounded chunks
  and preserve returned cursors only within the current extraction context.
- Do not access a live library database directly while the Calibre GUI is open. Route library work
  through the Content Server.
- `CALIBRE_MCP_ENABLE_WRITE=1` reflects explicit user authorization to expose write tools. Actual
  modifications also require the Calibre Content Server to allow local write access.
- Preview bulk, merge, remove, ISBN, and bundle operations before
  applying them and obtain confirmation for destructive changes.

## Tool routing

| Need | Tool/path |
|---|---|
| Connection check | `mcp__calibre__calibre_ping` |
| Find by title/author/tag/query | `mcp__calibre__calibre_search`, `mode: meta` |
| Exact words in books | `mcp__calibre__calibre_search`, `mode: fts` |
| Meaning-based discovery | `mcp__calibre__calibre_semantic_search` |
| Book metadata and formats | `mcp__calibre__calibre_get_book` |
| Outline or excerpts | `mcp__calibre__calibre_get_content` |
| Figures and illustrations | `mcp__calibre__calibre_get_figures` |
| Tags/authors/series schema | `mcp__calibre__calibre_list_categories` |
| Duplicate or quality audit | `mcp__calibre__calibre_find_duplicates`, `mcp__calibre__calibre_quality_report` |
| Metadata proposal | `mcp__calibre__calibre_recover_metadata`, `mcp__calibre__calibre_extract_isbn` |
| Search index | `mcp__calibre__calibre_build_index` |

For book hierarchy or TOC/spine analysis, use `$calibre-analyze-book-structure`. For Calibre
conversion selectors or EPUB package queries, use `$calibre-write-xpath`.

## Search sequence

1. Resolve a likely book with a small metadata search.
2. Confirm the record and formats.
3. Search inside the selected book with FTS or semantic scope.
4. Retrieve only the passages needed for the task.
5. Cite book identity and stable locations returned by the server; do not dump long copyrighted
   passages.

## Local CLI escape hatch

Use Calibre CLI only for file-level conversion/export or operations not exposed by MCP. If the GUI
is running, use the Content Server library URL for `calibredb` rather than `--library-path`.
`ebook-convert input output` is file-level and can operate on a copy without opening the library DB.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
