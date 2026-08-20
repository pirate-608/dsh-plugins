# @pirate-608/dsh-modlens

基于 ModLens 3.22.0 窄派生的 DSH 文本优先视觉桥，只保留三条命名路线，默认顺序为 `codex → openai → ollama`，不包含 Gemini 或 Antigravity provider。

```powershell
dsh plugin --profile web add @pirate-608/dsh-modlens
```

路线通过 profile patch 配置。本地 DSH 复用必须显式设置 `consent: true`，但图片仍可能上传并消耗远端账户额度；OpenAI-compatible 使用 DSH credential reference；Ollama 使用 loopback 原生 `/api/chat`，不会自动拉取模型。

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

本包不伪造多模态 LLM route。文本模型粘贴图片时会得到私有引用，`modlens_read_image` 返回结构化证据，证据作为普通工具结果进入 Session 日志。
