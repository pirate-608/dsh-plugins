---
name: everything-search
description: Find and count local Windows files and folders through the voidtools Everything index and ES command-line interface. Use when the user asks to locate files, discover folders, search by filename, extension, size or modified date, find recent local artifacts, count matching paths, or perform fast machine-wide or path-scoped file discovery without scanning the filesystem recursively.
---

# Everything Search

Use the plugin's read-only wrapper around `es.exe`. It returns structured JSON, limits output,
blocks Everything control commands, and reports missing ES or Everything IPC with actionable errors.
Do not use it to delete, move, open, or modify results.

## Prerequisites

Everything and the ES command-line interface are user-installed Windows programs; the plugin does
not bundle either binary. Everything must be running in the user's interactive session so ES can
reach its IPC window. Never start, exit, reindex, or reconfigure Everything unless the user asks.

Resolve `<plugin-root>` as the directory two levels above this skill directory. Run a diagnostic
before the first search in a task or after any IPC error:

```text
python <plugin-root>/scripts/everything_search.py doctor
```

If `everything_ipc_ready` is false, ask the user to start Everything and retry. Do not fall back to
a slow whole-disk recursive scan unless the user explicitly requests that alternative.

## Search

Use a bounded search:

```text
python <plugin-root>/scripts/everything_search.py search --query "<expression>" --max-results 100
```

Add only the options needed:

- `--path <existing-directory>` scopes results to a folder or drive.
- `--kind file|directory|any` filters object type.
- `--sort date-modified --order descending` returns newest results first.
- `--offset <n>` and `--max-results <1..1000>` page through large result sets.
- `--regex`, `--case-sensitive`, `--whole-word`, `--match-path`, or `--diacritics` enable ES modes.
- `--instance <name>` targets a named Everything instance.

Prefer a path scope when the user names a location. Otherwise search the whole index with a small
limit, summarize the best matches, and page only when necessary. Never issue an empty unbounded
query.

Useful Everything expressions:

- `report ext:pdf;docx`: matching documents.
- `dm:today ext:py`: Python files modified today.
- `size:>100mb video:`: large videos.
- `project | workspace`: either term.
- `invoice !draft`: include invoice and exclude draft.
- `content:needle ext:txt`: content search; warn that content is not indexed and can be slow.

Queries beginning with `-`, `/`, or `about:` are intentionally rejected because Everything can
treat them as options or commands. Express those searches with filename terms or functions.

## Count

When the user needs only a total, avoid returning paths:

```text
python <plugin-root>/scripts/everything_search.py count --query "ext:py" --path <workspace> --kind file
```

## Result handling

The `search` response contains `returned` plus `results[]` with `name`, `path`, `full_path`, `kind`,
`extension`, `size`, ISO-8601 creation/modification dates, and Windows attributes. Treat results as
index data: verify a path with a filesystem check before reading or changing it because the index
can briefly contain stale entries. Present a short ranked list and mention the scope and filters.

Official references:

- ES CLI: https://github.com/voidtools/ES
- Search syntax: https://www.voidtools.com/support/everything/searching/


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
