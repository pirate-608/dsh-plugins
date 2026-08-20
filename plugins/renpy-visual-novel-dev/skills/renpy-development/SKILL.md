---
name: renpy-development
description: Develop, review, and maintain Ren'Py visual novel projects. Use when the user asks about Ren'Py, .rpy/.rpym scripts, visual novel routes, screens, GUI customization, images/audio assets, localization, Ren'Py lint/build/test workflows, or this GoldenFall-style template project structure.
---

# Ren'Py Visual Novel Development

Use this skill whenever a task involves a Ren'Py visual novel project.

## Reference Sources

Prefer local project evidence first, then official Ren'Py documentation when exact syntax, commands, or behavior matter:

- Main docs: https://www.renpy.org/doc/html/
- Quickstart and template structure: https://www.renpy.org/doc/html/quickstart.html
- Language basics: https://www.renpy.org/doc/html/language_basics.html
- Screen language and GUI: https://www.renpy.org/doc/html/screens.html
- CLI, lint, translations, builds: https://www.renpy.org/doc/html/cli.html
- Build configuration: https://www.renpy.org/doc/html/build.html

If the user asks for latest Ren'Py behavior, version-specific APIs, packaging rules, Android/iOS/Web build instructions, or a direct quote/link, verify against the official docs before answering.

## Template Project Shape

Treat the current workspace's structure as the default template:

```text
project-root/
  game/
    script.rpy
    screens.rpy
    gui.rpy
    options.rpy
    README.md
    gui/
    audio/references/
    tl/
    saves/
    cache/
```

Important conventions:

- Root files are minimal; most source work belongs under `game/`.
- Narrative starts from `label start:` unless the user has introduced another entry label.
- Core game metadata and build settings live in `game/options.rpy`.
- UI and screen changes usually belong in `game/screens.rpy`, `game/gui.rpy`, or `game/gui/`.
- `game/saves/`, `game/cache/`, logs, generated translation files, and generated build outputs should not be treated as authored source.
- Compiled `.rpyc` and `.rpymc` files can matter for released save compatibility, but do not edit them by hand.

## Workflow
   - Route image creation, character expression derivation, chroma-key cleanup,
     deterministic resizing, and asset provenance through the companion
     `renpy-asset-generation` skill. Keep script authoring and asset registration
     in the bundled `renpy` MCP.
   - Prefer the bundled `renpy` MCP tools when available. Begin with
     `mcp__renpy__get_project_overview`, then use focused readers such as `mcp__renpy__read_label`,
     `mcp__renpy__read_screen`, `mcp__renpy__list_audio`, and `mcp__renpy__find_invalid_jumps` before editing.
   - The MCP binds to the active DSH workspace and discovers a project-local
     SDK under `.tools/renpy-mcp/sdk-cache/`. Set `RENPY_PROJECT` or
     `RENPY_SDK` only when automatic discovery cannot identify them.

1. Inspect before editing:
   - Run `rg --files` to map the project.
   - Read relevant `.rpy` and `.rpym` files before changing them.
   - Use `scripts/inspect_renpy_project.py <project-root>` from this plugin when a quick structural audit helps.

2. Preserve Ren'Py script style:
   - Use spaces for indentation. Ren'Py blocks are indentation-sensitive.
   - Keep labels, menus, Python blocks, screen language, and init-time declarations visually separated.
   - Prefer top-level `define`, `default`, `image`, `transform`, and `init python:` declarations when appropriate.
   - Avoid changing save-sensitive labels, persistent variable names, and released dialogue structure unless the user is intentionally migrating content.

3. Narrative edits:
   - Keep dialogue readable in short beats.
   - Use `Character` definitions instead of repeated literal speaker names for recurring cast members.
   - For routes, use clear labels and jumps/calls. Keep branch flags in `default` variables unless an init-time constant is required.
   - When adding menus, make choices concise and ensure every branch returns, jumps, or rejoins intentionally.

4. Visual and audio assets:
   - Follow Ren'Py image-name conventions: background files usually use the `bg` tag, and image names come from lowercased filenames without extensions.
   - Prefer `images/`, `audio/`, and `gui/` subfolders that match the existing project pattern.
   - Do not add large placeholder binaries unless the user asked for actual assets.
   - For user-provided reference audio/art, keep generated game-ready copies separate from `audio/references/` unless the project already uses it as source.
   - For generated raster art, use `renpy-asset-generation`; never introduce a
     Gemini/Nano Banana dependency or silently fall back to an API-key-based image service.

5. GUI and screens:
   - Use existing `gui.rpy` variables and `screens.rpy` patterns before introducing new UI systems.
   - Keep desktop and phone GUI assets in their matching `game/gui/` and `game/gui/phone/` paths when both exist.
   - Test text fit mentally for Chinese and English strings; visual novel UI often breaks first at translations and long names.

6. Localization:
   - Recognize `game/tl/<language>/` as translation output.
   - Avoid editing generated translation skeletons unless the user is localizing content.
   - When adding translatable strings to options or UI, preserve `_()` and `_p()` patterns already used by the template.
   - When CJK text is present, confirm that the project bundles or explicitly
     configures a licensed CJK-capable font. Warn when none is detected; do not
     download a font automatically.

7. Verification:
   - If a Ren'Py SDK path is available, prefer the official CLI:
     - Windows run: `.\lib\py3-windows-x86_64\python.exe renpy.py <project-root> run`
   - Prefer MCP verification when available: `mcp__renpy__get_lint_report`,
     `mcp__renpy__find_invalid_jumps`, `mcp__renpy__find_missing_assets`, and `mcp__renpy__get_scaffold_status`.
     Use `mcp__renpy__launch_preview`, `mcp__renpy__get_preview_status`, and `mcp__renpy__stop_preview` for a
     controlled playtest. Use `mcp__renpy__warp_to` to inspect a label without replaying
     earlier scenes.
   - For runtime visual verification, prefer the optional `renforge` MCP:
     inspect `mcp__renforge__renforge_info`, launch with `mcp__renforge__renforge_launch`, poll
     `mcp__renforge__renforge_launch_status`, then use `mcp__renforge__renforge_screenshot`,
     `mcp__renforge__renforge_scene_tree`, and `mcp__renforge__renforge_measure`. Stop the session with
     `mcp__renforge__renforge_stop`. If RenForge is unavailable or cannot install offline,
     report the degradation and continue with `mcp__renpy__launch_preview`, `mcp__renpy__warp_to`, and
     static diagnostics from the bundled `renpy` MCP.
     - Windows lint: `.\lib\py3-windows-x86_64\python.exe renpy.py <project-root> lint`
     - Windows distribute: `.\lib\py3-windows-x86_64\python.exe renpy.py launcher distribute <project-root> --destination <output>`
   - If the SDK is not available, run static checks only and clearly report that runtime lint/build was not executed.
   - For syntax-sensitive edits, scan for tabs, unbalanced quotes, missing colons after labels/menus/if blocks, and branches without exits.

## Common Tasks

### Add a Character

- Add `define <id> = Character("<display name>", color="#rrggbb")` near other character definitions.
- Use the short id for dialogue.
- If a side image or voice prefix is needed, follow existing project conventions first.

### Add a Route

- Add or update a `menu:` at the branch point.
- Store route state in `default` variables if the value participates in rollback or saves.
- Put route bodies in labels such as `label route_<name>:` and rejoin with a shared label when useful.

### Add Assets

- Place background images under `game/images/` or the existing asset folder.
- Name files so Ren'Py auto-defines predictable image names, such as `bg classroom.png` or `<character> happy.png`.
- Update script with `scene`, `show`, `hide`, and `with` statements in small, readable moments.

### Prepare a Build

- Review `game/options.rpy` for `config.name`, `config.version`, `build.name`, `config.window_icon`, and `build.classify`.
- Exclude source-only files with `build.classify(..., None)`.
- Only archive assets with `build.archive`/`build.classify` when the project needs that packaging behavior.
- Preserve `.rpyc` considerations for already released games.

## Response Style

When answering the user:

- Be specific about which files changed or need attention.
- Prefer small, directly usable Ren'Py snippets over abstract explanation.
- Mention when a recommendation comes from official docs versus local project inference.
- After installing or updating this plugin, start a new DSH task before
  expecting the bundled MCP tool namespace to appear.
- If you cannot run the Ren'Py SDK, say so plainly and provide the exact command the user can run.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
