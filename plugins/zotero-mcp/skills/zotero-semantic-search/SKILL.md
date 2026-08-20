---
name: zotero-semantic-search
description: Configure, diagnose, build, refresh, and query the Zotero MCP semantic index using the local Ollama bge-m3:latest embedding model. Use when conceptual Zotero search is unavailable or stale, when indexing new library content, when checking Chroma database status, or when troubleshooting Ollama, embedding-dimension, and semantic retrieval problems.
---

# Zotero Semantic Search

Keep embeddings local. Use Ollama at `http://127.0.0.1:11434` with `bge-m3:latest`; do not switch to
a cloud embedding provider unless the user explicitly requests it.

## Workflow

1. Run `../../scripts/zotero-doctor.ps1` or check the equivalent conditions: `uvx` exists, Zotero is
   running with its local API enabled, Ollama responds, and `bge-m3:latest` is installed.
2. Call `mcp__zotero__zotero_get_search_database_status`. An empty database is not an MCP failure.
3. Build or incrementally refresh with `mcp__zotero__zotero_update_search_database`; use full text when local PDF
   content should be searchable. The deterministic CLI equivalent is
   `../../scripts/zotero-index.ps1 index`.
4. Query with `mcp__zotero__zotero_semantic_search`, then retrieve authoritative metadata and relevant source text
   before drawing conclusions.
5. Report model, index size, update result, and any skipped or failed items.

## Rebuild rules

- Use incremental indexing by default.
- Rebuild only when the embedding provider/model or vector dimension changed, the database is
  demonstrably inconsistent, or the user explicitly requests it.
- Explain that rebuilding replaces the semantic index but does not delete Zotero library items.
- Do not invoke interactive upstream `setup` from an Agent session because it can edit external
  client configuration. Use the plugin environment and bounded scripts instead.
- If Zotero is closed, keep existing-index queries available when possible, but do not claim that
  the index is current.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
