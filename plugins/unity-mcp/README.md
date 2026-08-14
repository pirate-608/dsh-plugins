# @pirate-608/dsh-unity-mcp

English | [简体中文](README.zh-CN.md)

A preset-scoped Unity MCP tool and skill pack for DeepSeek Harness. It derives a `unity` agent preset from the `standard` preset shipped by the currently installed DSH version, so ordinary sessions do not receive Unity tools or their schema cost.

## Requirements

- DSH `>=0.0.1-rc.5 <0.2.0`
- Node.js 22.19+ or 24+
- `uvx` and Python 3.10+
- MCP for Unity installed and enabled in the Unity project

The generated preset resolves the MCP and filesystem-skill plugins from the active DSH installation, then starts `mcpforunityserver==10.1.2` over stdio with project-scoped tools. This avoids mixing DSH rc generations. The first `uvx` start may require network access.

## Install

```sh
dsh plugin --profile web add @pirate-608/dsh-unity-mcp
dsh plugin --profile web exec dsh-unity-mcp preset install
```

Create a new WebUI session and select the `unity` preset. The generated MCP tools are named `mcp__unity__<raw-name>`.

Manage the preset with:

```sh
dsh plugin --profile web exec dsh-unity-mcp preset status
dsh plugin --profile web exec dsh-unity-mcp preset update
dsh plugin --profile web exec dsh-unity-mcp preset remove
```

`update` regenerates from the currently installed DSH `standard` preset. Local changes cause update/removal to stop. `--force` preserves the complete modified preset as a timestamped backup before continuing.

Remove the preset before removing the package:

```sh
dsh plugin --profile web exec dsh-unity-mcp preset remove
dsh plugin --profile web remove @pirate-608/dsh-unity-mcp
```

## Text-first multimodal fallback

The skills assume the active model cannot inspect images. DSH currently renders non-text MCP blocks as placeholders, so screenshot tools use file output and return a path. A path is not visual proof: the agent reports structural and runtime verification separately and leaves visual verification pending until the user or an explicitly image-capable host confirms it.

The plugin never automatically uploads screenshots, invokes OCR, or calls another vision provider.

## Security

MCP tool calls pass through DSH's tool approval pipeline. The `uvx` MCP process and Unity Editor run outside DSH's filesystem sandbox and can modify the connected Unity project. Use a dedicated preset, review approval prompts, and keep source control available.

## Known limitations

- DSH bridges MCP Tools only; Resources and Prompts are unavailable.
- The plugin cannot enumerate Unity instances. It can select a known id with `mcp__unity__set_active_instance`.
- Inline screenshot data is deliberately unused.
- A running session retains the preset generation it started with; updates affect new sessions.
