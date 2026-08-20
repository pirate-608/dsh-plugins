---
name: latex-workflows
description: Use when a task involves compiling, validating, troubleshooting, or preparing LaTeX projects in DSH. Prefer bundled Tectonic for simple projects, fall back to detected local MiKTeX for fuller projects, validate local LaTeX readiness, and ask the user to verify the MiKTeX path when no usable system LaTeX installation is present.
---

# LaTeX Workflows

## When To Use

Use this skill when the user asks DSH to build, validate, debug, or prepare a LaTeX project, especially `.tex` files, BibTeX/Biber bibliographies, packages, fonts, indexes, glossaries, or PDF generation.

## Tool Preference

1. Prefer bundled Tectonic first for simple projects.
   - Use Tectonic when the project is a single main `.tex` file, uses ordinary packages, and does not require shell escape, `makeindex`, `makeglossaries`, `biber`, `minted`, custom engines, custom class installation, or project-specific build orchestration.
   - Look first for a bundled Tectonic executable in DSH or workspace dependency locations, then for `tectonic` on `PATH`.
   - Compile with a deterministic output directory when possible, for example `tectonic main.tex --outdir build`.

2. Fall back to local MiKTeX for fuller projects.
   - Use MiKTeX when the project needs `latexmk`, `pdflatex`, `xelatex`, `lualatex`, `bibtex`, `biber`, `makeindex`, `makeglossaries`, `minted`, shell escape, project build files, or packages that Tectonic cannot resolve.
   - Detect MiKTeX from `PATH` first, then common Windows installation roots such as `%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64`, `%PROGRAMFILES%\MiKTeX\miktex\bin\x64`, and `%PROGRAMFILES(X86)%\MiKTeX\miktex\bin`.
   - Prefer `latexmk -pdf` when available. Otherwise run the needed engine and bibliography/index tools explicitly.

3. Ask for user verification only after detection fails.
   - If no usable system LaTeX installation is found and the project is too full-featured for bundled Tectonic, ask the user to verify the MiKTeX path.
   - Keep the question concise and include the paths already checked.
   - Do not guess a MiKTeX path or add one to `PATH` permanently without user confirmation.

## Readiness Check

Before compiling a non-trivial project, validate local LaTeX readiness:

1. Identify the main `.tex` file.
   - Prefer `latexmkrc`, `.latexmkrc`, `tectonic.toml`, `Tectonic.toml`, or obvious roots containing `\documentclass`.
   - If several main files are plausible, choose the one matching the user request or ask one short clarifying question.

2. Run the helper script when available:

```powershell
python scripts/check_latex_readiness.py <project-path>
```

   On Windows, confirm the Python command is the intended interpreter before assuming package
   availability:

```powershell
where.exe python
python --version
```

   If DSH was started from an environment that initialized Conda or MSYS first, `python` may
   resolve to that interpreter instead of the user's system Python. In that case, either restart
   DSH after fixing the shell startup environment or call the intended interpreter explicitly.
   This plugin's readiness helper uses only the Python standard library, so it does not require
   extra packages.

3. Confirm these capabilities as relevant:
   - Tectonic executable available for simple projects.
   - MiKTeX executable directory detected for full projects.
   - `latexmk`, engine command, bibliography command, and index/glossary tools are present when the project requires them.
   - Output directory is writable.

4. Report readiness in practical terms:
   - `ready-with-tectonic` for simple projects Tectonic can handle.
   - `ready-with-miktex` for fuller projects with required MiKTeX commands available.
   - `needs-miktex-path` when the project needs a system LaTeX toolchain but no usable MiKTeX installation was detected.

## Build Workflow

1. Inspect project structure with `rg --files`.
2. Classify the project as simple or full-featured.
3. Run readiness validation.
4. Compile:
   - Simple: Tectonic first.
   - Full-featured: MiKTeX/latexmk first.
5. Inspect logs for missing packages, engine mismatches, bibliography errors, shell-escape requirements, and PDF output.
6. Iterate only on files relevant to the LaTeX build.
7. Deliver the generated PDF path and a short summary of warnings or remaining issues.

## Safety Notes

- Do not run package-manager updates or install missing packages without explicit user approval.
- Do not enable shell escape unless the project requires it and the user approves or the repository clearly expects it.
- Keep generated build artifacts in a `build`, `out`, or project-native output directory.
- Preserve user edits and unrelated files.

## Maintenance Notes

- Validate plugin edits with `python <plugin-creator>/scripts/validate_plugin.py <plugin-path>`.
- Validate this skill with `python <skill-creator>/scripts/quick_validate.py <skill-path>`.
- The plugin validator imports `PyYAML`; if the active Python cannot import `yaml`, install
  `PyYAML` into the intended user-level Python environment. Do not update `pip` unless the user
  explicitly approves the required administrator step.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
