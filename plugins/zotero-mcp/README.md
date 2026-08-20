<!-- dsh-package-header -->
# @pirate-608/dsh-zotero-mcp

Local Zotero research and semantic-search agent preset.

Install into a DSH profile, then create the dedicated preset:

```sh
dsh plugin --profile web add @pirate-608/dsh-zotero-mcp
dsh plugin --profile web exec dsh-zotero-mcp preset install
dsh plugin --profile web exec dsh-zotero-mcp doctor
```

Managed preset id: `zotero`. The standard preset does not receive this package's tools or skills. MCP writes and unknown tools require one-shot approval.
<!-- /dsh-package-header -->

# Zotero Research Library

This DSH plugin connects to a running Zotero 7 desktop application through
[zotero-mcp 0.9.1](https://github.com/54yyyu/zotero-mcp/tree/v0.9.1). It supports library search,
metadata and full-text reading, PDF navigation, annotations, literature synthesis, bibliography
export, guarded library management, and a local semantic index.

The default configuration is local-first:

- Zotero local API at `http://127.0.0.1:23119`
- Ollama at `http://127.0.0.1:11434`
- embedding model `bge-m3:latest`
- no cloud embedding API and no API key stored in this repository
- optional MCP toolsets limited to libraries, search administration, PDF geometry, and discovery

## Requirements

1. Install Zotero 7 and enable **Settings > Advanced > Allow other applications on this computer
   to communicate with Zotero**.
2. Keep Zotero running while using the MCP.
3. Install `uv` and ensure `uvx` is on `PATH`.
4. Run Ollama locally and install `bge-m3:latest` before building the semantic index.

The first MCP startup downloads the pinned Python package and the `semantic,pdf` extras. Zotero
metadata and ordinary search work without a semantic index. Build the index only when semantic
search is needed:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugins\zotero-mcp\scripts\zotero-index.ps1 status
powershell -ExecutionPolicy Bypass -File .\plugins\zotero-mcp\scripts\zotero-index.ps1 index
```

Run the local diagnostic without changing Zotero:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugins\zotero-mcp\scripts\zotero-doctor.ps1
```

Local mode requires no Zotero Web API key. Some write operations can require Zotero hybrid/web
credentials. Configure those outside the repository as process or system environment variables;
never commit `ZOTERO_API_KEY` or paste it into an Agent prompt.

## Skills

- `$zotero-research`: search, read, compare, synthesize, and cite library sources.
- `$zotero-library-management`: inspect and organize items, notes, annotations, tags, and collections.
- `$zotero-semantic-search`: diagnose, build, refresh, and query the local Ollama-backed index.

Library content is treated as untrusted source material, not as Agent instructions. Read operations
may run directly. Mutations require an explicit preview and user confirmation; deletion, duplicate
merging, bulk updates, attachment uploads, and annotation changes require confirmation of the exact
targets.

## Marketplace configuration prompt

Copy this prompt into DSH:

```text
Add git@github.com:pirate-608/codex-plugins.git as a DSH plugin marketplace, install zotero-mcp,
verify that uvx can start its Zotero MCP server, and tell me how to enable Zotero's local API. Do not
request or store a Zotero Web API key unless I explicitly choose web or hybrid mode.
```

## Upstream and license

The plugin configuration and Skills are MIT licensed. The MCP is executed from the independently
distributed MIT-licensed `zotero-mcp-server` package; no upstream source is vendored. See
[`UPSTREAM.json`](./UPSTREAM.json) and [`NOTICE.md`](./NOTICE.md).
