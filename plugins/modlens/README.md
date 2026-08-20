# @pirate-608/dsh-modlens

A text-first vision bridge for DeepSeek Harness, narrowly derived from ModLens 3.22.0. It provides three named routes in the default order `codex → openai → ollama` and never installs Gemini or Antigravity providers.

```sh
dsh plugin --profile web add @pirate-608/dsh-modlens
```

Configure routes in the profile patch. DSH reuse requires `consent: true`; this reuses a local CLI login but may still upload the image and spend remote account quota. OpenAI-compatible credentials are DSH credential references. Ollama uses its native loopback `/api/chat` API and never pulls a model automatically.

```yaml
- id: pirate-modlens
  name: '@pirate-608/dsh-modlens'
  config:
    routes:
      codex: { type: codex-cli, consent: true }
      openai:
        type: openai-compatible
        baseUrl: https://vision.example.com/v1
        model: vision-model
        credentialRef: OPENAI_VISION_API_KEY
        structuredOutput: true
      ollama:
        type: ollama
        baseUrl: http://127.0.0.1:11434
        model: qwen3-vl
    failover: [codex, openai, ollama]
```

The package does not synthesize a fake multimodal LLM route. Text-only paste is converted to a private opaque reference, `modlens_read_image` returns structured evidence, and that ordinary tool result is retained in the session log.
