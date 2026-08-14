---
name: unity-build-release
description: Configure, build, validate, and package Unity player releases through Unity MCP. Use for Windows, macOS, Linux, Android, iOS, WebGL, UWP, tvOS, visionOS, or dedicated-server builds; Build Profiles, build scenes, product and bundle settings, versioning, scripting backend, architecture, development builds, batch builds, build status or cancellation, release smoke tests, and diagnosing or preparing publish-ready artifacts.
---

# Unity Build & Release

Produce a traceable build from an explicit target configuration and verify both the build report and runnable artifact.

## Preflight

1. Read editor state, project info, installed packages, active build target, build settings, enabled scenes, and available Build Profiles.
2. Confirm target platform, output location, version, bundle/application identifier, architecture, scripting backend, development/release intent, and server/player subtarget.
3. Confirm the required Unity platform module and SDK/toolchain exist. Do not install external SDKs or change signing credentials without user authorization.
4. Run relevant EditMode and PlayMode tests. Read console errors and resolve compile failures before building.
5. Validate that every enabled scene exists and starts in the intended order.

## Build Workflow

1. Query `mcp__unity__manage_build(action="platform")`, `settings`, `scenes`, and `profiles` before mutating them.
2. Prefer a named Unity 6 Build Profile when the project uses profiles; otherwise configure target-specific settings explicitly.
3. Switch platform only when needed and wait for imports to finish.
4. Start `mcp__unity__manage_build(action="build")` with an explicit output path and options. Use development or deep profiling only for diagnostic artifacts.
5. Poll `mcp__unity__manage_build(action="status")` by job ID. Use cancel only when the user requests it or continuing is clearly unsafe.
6. For multi-platform work, use batch builds only after one target succeeds and output directories are isolated.
7. Inspect the build result, warnings, errors, duration, size, scenes, and output files.

## Release Rules

- Keep secrets, signing keys, passwords, provisioning profiles, and store credentials out of prompts, logs, and source control.
- Treat signing, store upload, notarization, and external publishing as separate authorized steps. This skill may prepare artifacts without publishing them.
- Do not silently change bundle identifiers, version codes, scripting backend, managed stripping, architectures, or graphics APIs.
- Use clean builds for release candidates when stale output is plausible.
- Preserve a reproducible record of Unity version, packages, profile/settings, source revision when available, and build options.
- A successful build API response is not a smoke test. Launch or otherwise inspect the artifact when the platform permits.

## Completion Gate

Require a successful build report, expected output files, no unexplained errors, a smoke-test result or explicit reason it could not run, and a concise release manifest of target, version, profile, backend, scenes, output path, and remaining signing/publishing steps. A file screenshot is not visual proof unless the user or a verified multimodal host confirms it.

Read the shared [tool reference](../unity-mcp-skill/references/tools-reference.md) for exact build actions and options.
