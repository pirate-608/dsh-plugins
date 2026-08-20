<!-- dsh-package-header -->
# @pirate-608/dsh-everything-search

Fast local Windows file search through Everything and ES.

Install into a DSH profile, then create the dedicated preset:

```sh
dsh plugin --profile web add @pirate-608/dsh-everything-search
dsh plugin --profile web exec dsh-everything-search preset install
dsh plugin --profile web exec dsh-everything-search doctor
```

Managed preset id: `everything-search`. The standard preset does not receive this package's tools or skills. MCP writes and unknown tools require one-shot approval.
<!-- /dsh-package-header -->

# Everything Search

Windows-only DSH workflow for fast local file and folder discovery through the voidtools
Everything index and its `es.exe` command-line interface.

## Requirements

- [Everything](https://www.voidtools.com/) installed and running in the interactive user session.
- [ES](https://github.com/voidtools/ES) installed on `PATH`, or its full path set in
  `EVERYTHING_ES_PATH`.
- Python 3.10 or newer.

The plugin does not bundle or automatically start Everything or ES. It performs read-only queries
and blocks ES/Everything control commands.

## Diagnostic and direct use

```powershell
python .\scripts\everything_search.py doctor
python .\scripts\everything_search.py search --query "ext:pdf report" --path D:\Documents --kind file --max-results 25
python .\scripts\everything_search.py count --query "ext:py" --path D:\projects --kind file
```

Every command writes structured JSON. Search results are limited to 100 by default and 1000 at
most. Use `--help` on the script or its subcommands for the full option list.

## Tested environment

- ES 1.1.0.37
- Everything 1.4.1.1032

Other compatible ES/Everything releases may work, but are not bundled or pinned by the plugin.
