/** Apply reproducible DSH tool qualification and remove Codex-only assumptions. */

import { readFile, readdir, writeFile } from 'node:fs/promises'

const roots = new URL('../plugins/', import.meta.url)
const prefixRules = {
  'adobe-after-effects': [{ pattern: /\bae_[A-Za-z0-9_]+\b/g, server: 'after_effects' }],
  'adobe-photoshop': [{ pattern: /\bphotoshop_[A-Za-z0-9_]+\b/g, server: 'photoshop' }],
  'calibre-library-tools': [{ pattern: /\bcalibre_[A-Za-z0-9_]+\b/g, server: 'calibre' }],
  'zotero-mcp': [{ pattern: /\bzotero_[A-Za-z0-9_]+\b/g, server: 'zotero' }],
  'zju-learning-tools': [{ pattern: /\bzju_[A-Za-z0-9_]+\b/g, server: 'zju_learning' }],
  'solidworks-automation': [{ pattern: /\bsolidworks_[A-Za-z0-9_]+\b/g, server: 'solidworks' }],
}

const exactRules = {
  'adobe-premiere': {
    server: 'premiere_pro',
    tools: ['assemble_product_spot', 'detect_silence', 'export_sequence', 'get_project_info', 'get_render_queue_status', 'validate_project_for_export', 'get_active_sequence', 'list_project_items', 'list_sequences'],
  },
  'autocad-mcp': {
    server: 'autocad',
    tools: ['drawing', 'entity', 'layer', 'block', 'annotation', 'pid', 'view', 'system'],
  },
  'renpy-visual-novel-dev': {
    server: 'renpy',
    tools: ['add_image_alias', 'find_missing_assets', 'get_lint_report', 'get_media_invariants', 'get_project_overview', 'find_invalid_jumps', 'get_preview_status', 'get_scaffold_status', 'launch_preview', 'list_audio', 'read_label', 'read_screen', 'stop_preview', 'warp_to'],
  },
}

for (const plugin of await readdir(roots, { withFileTypes: true })) {
  if (!plugin.isDirectory() || plugin.name === 'unity-mcp') continue
  const skillRoot = new URL(`${plugin.name}/skills/`, roots)
  await walk(skillRoot, plugin.name)
  await rewriteHostTerms(new URL(`${plugin.name}/`, roots))
}

async function walk(directory, pluginName) {
  let entries
  try {
    entries = await readdir(directory, { withFileTypes: true })
  } catch (error) {
    if (error?.code === 'ENOENT') return
    throw error
  }
  for (const entry of entries) {
    const target = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, directory)
    if (entry.isDirectory()) await walk(target, pluginName)
    else if (entry.name.endsWith('.md')) await rewrite(target, pluginName)
  }
}

async function rewrite(file, pluginName) {
  let text = await readFile(file, 'utf8')
  for (const rule of prefixRules[pluginName] ?? []) {
    text = text.replace(rule.pattern, value => value.startsWith(`mcp__${rule.server}__`) ? value : `mcp__${rule.server}__${value}`)
  }
  const exact = exactRules[pluginName]
  if (exact !== undefined) {
    for (const tool of exact.tools) {
      text = text.replace(new RegExp(`(?<!mcp__${exact.server}__)\\b${tool}\\b`, 'g'), `mcp__${exact.server}__${tool}`)
    }
  }
  if (pluginName === 'renpy-visual-novel-dev') {
    for (const tool of ['renforge_info', 'renforge_launch', 'renforge_launch_status', 'renforge_screenshot', 'renforge_scene_tree', 'renforge_measure', 'renforge_stop']) {
      text = text.replace(new RegExp(`(?<!mcp__renforge__)\\b${tool}\\b`, 'g'), `mcp__renforge__${tool}`)
    }
  }
  text = text
    .replaceAll('computer-use', 'ModLens file evidence or explicit human review')
    .replaceAll('Windows computer control', 'the documented local installer')
    .replaceAll('Codex built-in image generation', 'an explicitly configured external image generator')
    .replaceAll('Codex image generation', 'an explicitly configured external image generator')
    .replaceAll('$CODEX_HOME/generated_images/', 'a user-confirmed source path outside the project')
    .replaceAll('skills/.system/imagegen/scripts/remove_chroma_key.py', 'a user-selected background-removal tool')
    .replaceAll('Codex', 'DSH')
    .replaceAll('.codex', '.dsh')
  if (file.pathname.endsWith('/SKILL.md') && !text.includes('<!-- dsh-visual-fallback -->')) {
    text += `\n\n<!-- dsh-visual-fallback -->\n## Visual evidence\n\nWhen a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call \`modlens_read_image\` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.\n`
  }
  await writeFile(file, text.trimEnd() + '\n')
}

async function rewriteHostTerms(directory) {
  let entries
  try {
    entries = await readdir(directory, { withFileTypes: true })
  } catch (error) {
    if (error?.code === 'ENOENT') return
    throw error
  }
  for (const entry of entries) {
    if (entry.isDirectory() && ['vendor', 'bin', 'assets'].includes(entry.name)) continue
    const target = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, directory)
    if (entry.isDirectory()) {
      await rewriteHostTerms(target)
      continue
    }
    if (!/\.(?:md|py|ps1|cjs|js)$/.test(entry.name)) continue
    let text = await readFile(target, 'utf8')
    text = text
      .replaceAll('CodexAutoCADMCP', 'DshAutoCADMCP')
      .replaceAll('CODEX_', 'DSH_')
      .replaceAll('Codex', 'DSH')
      .replaceAll('.codex', '.dsh')
      .replaceAll('premiere://config/get_instructions', 'the documented MCP Tools inventory')
    await writeFile(target, text.trimEnd() + '\n')
  }
}
