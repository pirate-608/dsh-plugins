<!-- dsh-package-header -->
# @pirate-608/dsh-premiere

Adobe Premiere Pro automation through a bundled CEP MCP bridge.

Install into a DSH profile, then create the dedicated preset:

```sh
dsh plugin --profile web add @pirate-608/dsh-premiere
dsh plugin --profile web exec dsh-premiere preset install
dsh plugin --profile web exec dsh-premiere doctor
```

Managed preset id: `premiere`. The standard preset does not receive this package's tools or skills. MCP writes and unknown tools require one-shot approval.

**Publication blocked:** this package remains private until its first-party license is resolved.
<!-- /dsh-package-header -->
