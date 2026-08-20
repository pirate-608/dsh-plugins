<!-- dsh-package-header -->
# @pirate-608/dsh-calibre-library-tools

Calibre library reading, analysis, and XPath workflows.

Install into a DSH profile, then create the dedicated preset:

```sh
dsh plugin --profile web add @pirate-608/dsh-calibre-library-tools
dsh plugin --profile web exec dsh-calibre-library-tools preset install
dsh plugin --profile web exec dsh-calibre-library-tools doctor
```

Managed preset id: `calibre-library`. The standard preset does not receive this package's tools or skills. MCP writes and unknown tools require one-shot approval.
<!-- /dsh-package-header -->
