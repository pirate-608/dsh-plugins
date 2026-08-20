/** Generate the mechanically identical package shells around migrated content. */

import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const root = new URL('../', import.meta.url)

const commonDoctor = (extra = []) => [{ label: 'Node.js', command: 'node', args: ['--version'] }, ...extra]
const mcp = (id, serverName, command, args, options = {}) => ({
  id,
  serverName,
  command,
  args,
  env: options.env ?? {},
  cwd: options.cwd ?? '',
  toolCallTimeoutMs: options.toolCallTimeoutMs ?? 300000,
  failOnStartupError: true,
})
const policy = (serverName, readOnly = [], ask = [], deny = []) => ({
  serverNames: [serverName], readOnly, ask, deny,
})

const packages = [
  {
    dir: 'everything-search', slug: 'everything-search', private: false, license: 'MIT',
    description: 'Fast local Windows file search through Everything and ES',
    preset: {
      id: 'everything-search', name: 'Everything Search', description: 'Local Windows file discovery with Everything.',
      providerName: 'everything-search-skills', platform: 'win32',
      doctor: commonDoctor([{ label: 'Everything ES CLI', command: 'es.exe', args: ['-version'] }]),
    },
  },
  {
    dir: 'latex-workflows', slug: 'latex-workflows', private: true, license: 'UNLICENSED',
    description: 'LaTeX compile, inspection, and PDF verification workflows',
    preset: {
      id: 'latex-workflows', name: 'LaTeX Workflows', description: 'Compile and validate LaTeX documents.',
      providerName: 'latex-workflows-skills',
      doctor: commonDoctor([
        { label: 'Tectonic', command: 'tectonic', args: ['--version'], optional: true },
        { label: 'pdfLaTeX', command: 'pdflatex', args: ['--version'], optional: true },
      ]),
    },
  },
  {
    dir: 'zotero-mcp', slug: 'zotero-mcp', private: false, license: 'MIT',
    description: 'Local Zotero research and semantic-search agent preset',
    preset: {
      id: 'zotero', name: 'Zotero Research', description: 'Research and safely organize a local Zotero library.',
      providerName: 'zotero-skills',
      mcpServers: [mcp('zotero-mcp', 'zotero', 'uvx', ['--from', 'zotero-mcp-server[semantic,pdf]==0.9.1', 'zotero-mcp-server', 'serve', '--transport', 'stdio'], {
        env: {
          ZOTERO_LOCAL: 'true', ZOTERO_MCP_TOOLSETS: 'libraries,search-admin,pdf-geometry,discovery',
          ZOTERO_EMBEDDING_MODEL: 'ollama', OLLAMA_EMBEDDING_MODEL: 'bge-m3:latest', OLLAMA_BASE_URL: 'http://127.0.0.1:11434',
        },
      })],
      policy: policy('zotero', [
        'mcp__zotero__zotero_search_items', 'mcp__zotero__zotero_semantic_search',
        'mcp__zotero__zotero_get_search_database_status', 'mcp__zotero__zotero_export_bibliography',
      ], ['mcp__zotero__zotero_update_search_database']),
      doctor: commonDoctor([{ label: 'uvx', command: 'uvx', args: ['--version'] }]),
    },
  },
  {
    dir: 'calibre-library-tools', slug: 'calibre-library-tools', private: false, license: 'MIT',
    description: 'Calibre library reading, analysis, and XPath workflows',
    preset: {
      id: 'calibre-library', name: 'Calibre Library', description: 'Read and analyze a Calibre library with writes disabled by default.',
      providerName: 'calibre-library-skills',
      mcpServers: [mcp('calibre-mcp', 'calibre', 'npx', ['-y', 'calibre-mcp@0.7.2'], {
        env: { CALIBRE_MCP_SERVER_URL: 'http://127.0.0.1:8080', CALIBRE_MCP_ENABLE_WRITE: '0' },
      })],
      policy: policy('calibre', [
        'mcp__calibre__calibre_ping', 'mcp__calibre__calibre_list_libraries', 'mcp__calibre__calibre_search',
        'mcp__calibre__calibre_get_book', 'mcp__calibre__calibre_get_content', 'mcp__calibre__calibre_get_figures',
        'mcp__calibre__calibre_list_categories', 'mcp__calibre__calibre_find_duplicates', 'mcp__calibre__calibre_quality_report',
      ], ['mcp__calibre__calibre_build_index']),
      doctor: commonDoctor([{ label: 'npx', command: 'npx', args: ['--version'] }]),
    },
  },
  {
    dir: 'adobe-after-effects', slug: 'after-effects', private: true, license: 'UNLICENSED',
    description: 'Adobe After Effects automation through ae-mcp',
    preset: {
      id: 'after-effects', name: 'After Effects', description: 'Inspect and automate Adobe After Effects.',
      providerName: 'after-effects-skills', platform: 'win32',
      mcpServers: [mcp('after-effects-mcp', 'after_effects', 'powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', './scripts/start-ae-mcp.ps1'], { cwd: '.' })],
      policy: policy('after_effects', ['mcp__after_effects__ae_get_project_info', 'mcp__after_effects__ae_get_active_composition']),
      runtime: {
        install: { command: 'powershell.exe', args: ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', './scripts/install-ae-mcp-runtime.ps1'], cwd: '.' },
        status: { command: 'powershell.exe', args: ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', './scripts/install-ae-mcp-runtime.ps1', '-CheckOnly'], cwd: '.' },
      },
      doctor: commonDoctor([{ label: 'PowerShell', command: 'powershell.exe', args: ['-NoLogo', '-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'] }]),
    },
  },
  {
    dir: 'adobe-photoshop', slug: 'photoshop', private: true, license: 'UNLICENSED',
    description: 'Adobe Photoshop automation through a local COM MCP bridge',
    preset: {
      id: 'photoshop', name: 'Photoshop', description: 'Inspect and edit Adobe Photoshop documents.',
      providerName: 'photoshop-skills', platform: 'win32',
      mcpServers: [mcp('photoshop-mcp', 'photoshop', 'powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', './scripts/start-photoshop-mcp.ps1'], { cwd: '.' })],
      policy: policy('photoshop', ['mcp__photoshop__photoshop_get_session_info']),
      runtime: {
        install: { command: 'powershell.exe', args: ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', './scripts/install-photoshop-mcp.ps1'], cwd: '.' },
        status: { command: 'powershell.exe', args: ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', './scripts/install-photoshop-mcp.ps1', '-CheckOnly'], cwd: '.' },
      },
      doctor: commonDoctor([{ label: 'PowerShell', command: 'powershell.exe', args: ['-NoLogo', '-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'] }]),
    },
  },
  {
    dir: 'adobe-premiere', slug: 'premiere', private: true, license: 'UNLICENSED',
    description: 'Adobe Premiere Pro automation through a bundled CEP MCP bridge',
    preset: {
      id: 'premiere', name: 'Premiere Pro', description: 'Inspect and edit Adobe Premiere Pro projects.',
      providerName: 'premiere-skills', platform: 'win32',
      mcpServers: [mcp('premiere-mcp', 'premiere_pro', 'node', ['./scripts/start-premiere-mcp.cjs'], { cwd: '.' })],
      policy: policy('premiere_pro', [
        'mcp__premiere_pro__get_project_info', 'mcp__premiere_pro__list_sequences',
        'mcp__premiere_pro__get_active_sequence', 'mcp__premiere_pro__list_project_items',
      ]),
      runtime: {
        install: { command: 'powershell.exe', args: ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', './scripts/install-premiere-bridge.ps1'], cwd: '.' },
      },
      doctor: commonDoctor([]),
    },
  },
  {
    dir: 'autocad-mcp', slug: 'autocad-mcp', private: true, license: 'UNLICENSED',
    description: 'AutoCAD and headless DXF automation through a text-first MCP preset',
    preset: {
      id: 'autocad', name: 'AutoCAD', description: 'Automate AutoCAD with text-first evidence and explicit approvals.',
      providerName: 'autocad-skills', platform: 'win32',
      mcpServers: [mcp('autocad-mcp', 'autocad', 'uv', ['run', '--project', './vendor/autocad-mcp', 'python', '-m', 'autocad_mcp'], {
        cwd: '.', env: { AUTOCAD_MCP_BACKEND: 'auto', AUTOCAD_MCP_IPC_DIR: 'C:/temp/dsh-autocad-mcp', AUTOCAD_MCP_IPC_TIMEOUT: '30', AUTOCAD_MCP_ONLY_TEXT: 'true' },
      })],
      policy: policy('autocad'),
      runtime: {
        install: { command: 'powershell.exe', args: ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', './scripts/install.ps1'], cwd: '.' },
      },
      doctor: commonDoctor([{ label: 'uv', command: 'uv', args: ['--version'] }]),
    },
  },
  {
    dir: 'solidworks-automation', slug: 'solidworks-automation', private: false, license: 'MIT',
    description: 'SolidWorks COM and MCP automation workflows',
    preset: {
      id: 'solidworks', name: 'SolidWorks', description: 'Automate SolidWorks parts, assemblies, drawings, and review.',
      providerName: 'solidworks-skills', platform: 'win32',
      mcpServers: [mcp('solidworks-mcp', 'solidworks', 'python', ['./mcp-server/server.py'], { cwd: './skills/solidworks-automation' })],
      policy: policy('solidworks', ['mcp__solidworks__solidworks_health_check', 'mcp__solidworks__solidworks_inspect_hole_features', 'mcp__solidworks__solidworks_inspect_motion_studies']),
      doctor: commonDoctor([{ label: 'Python', command: 'python', args: ['--version'] }]),
    },
  },
  {
    dir: 'renpy-visual-novel-dev', slug: 'renpy-visual-novel-dev', private: false, license: 'AGPL-3.0-only',
    description: 'RenPy development, preview, testing, and asset-integration workflows',
    preset: {
      id: 'renpy', name: 'RenPy Development', description: 'Develop and validate an explicit RenPy project root.',
      providerName: 'renpy-skills',
      mcpServers: [
        mcp('renpy-mcp', 'renpy', 'uv', ['run', '--project', './vendor/renpy-mcp', 'python', './scripts/start_renpy_mcp.py'], { cwd: '.', env: { RENPY_MCP_TIERS: '1,2,3' } }),
        mcp('renforge-mcp', 'renforge', 'uvx', ['renforge@0.7.0', 'serve'], { cwd: '.', toolCallTimeoutMs: 300000 }),
      ],
      policy: { serverNames: ['renpy', 'renforge'], readOnly: [], ask: [], deny: [] },
      runtime: {
        install: { command: 'uv', args: ['sync', '--project', './vendor/renpy-mcp', '--frozen'], cwd: '.' },
      },
      doctor: commonDoctor([{ label: 'uv', command: 'uv', args: ['--version'] }, { label: 'uvx', command: 'uvx', args: ['--version'] }]),
    },
  },
  {
    dir: 'zju-learning-tools', slug: 'zju-learning-tools', private: false, license: 'MIT',
    description: 'Read and separately approve bounded ZJU learning operations',
    preset: [
      {
        id: 'zju-read', name: 'ZJU Learning (Read)', description: 'Read ZJU course data without submission tools.',
        providerName: 'zju-read-skills', platform: 'win32',
        mcpServers: [mcp('zju-read-mcp', 'zju_learning', 'uv', ['run', '--project', './runtime', '--frozen', 'python', './scripts/start_mcp.py'], { cwd: '.', env: { ZJU_SUBMISSION_TOOLS: 'disabled' } })],
        policy: policy('zju_learning', [
          'mcp__zju_learning__zju_doctor', 'mcp__zju_learning__zju_auth_status', 'mcp__zju_learning__zju_list_terms',
          'mcp__zju_learning__zju_list_courses', 'mcp__zju_learning__zju_get_course', 'mcp__zju_learning__zju_list_todos',
          'mcp__zju_learning__zju_list_assignments', 'mcp__zju_learning__zju_get_assignment', 'mcp__zju_learning__zju_list_grades',
        ]),
        runtime: {
          install: { command: 'uv', args: ['sync', '--project', './runtime', '--frozen'], cwd: '.' },
        },
        doctor: commonDoctor([{ label: 'uv', command: 'uv', args: ['--version'] }]),
      },
      {
        id: 'zju-submit', name: 'ZJU Learning (Submit)', description: 'Prepare and submit one reviewed ordinary assignment with approval.',
        providerName: 'zju-submit-skills', platform: 'win32',
        mcpServers: [mcp('zju-submit-mcp', 'zju_learning', 'uv', ['run', '--project', './runtime', '--frozen', 'python', './scripts/start_mcp.py'], { cwd: '.', env: { ZJU_SUBMISSION_TOOLS: 'enabled' } })],
        policy: policy('zju_learning', ['mcp__zju_learning__zju_doctor', 'mcp__zju_learning__zju_auth_status'], [
          'mcp__zju_learning__zju_prepare_assignment_submission', 'mcp__zju_learning__zju_commit_assignment_submission',
        ]),
        runtime: {
          install: { command: 'uv', args: ['sync', '--project', './runtime', '--frozen'], cwd: '.' },
        },
        doctor: commonDoctor([{ label: 'uv', command: 'uv', args: ['--version'] }]),
      },
    ],
  },
]

const bin = `#!/usr/bin/env node
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { runPluginCli } from '@pirate-608/dsh-plugin-kit'

const packageRoot = fileURLToPath(new URL('../', import.meta.url))
const manifest = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'))
const raw = JSON.parse(await readFile(new URL('../preset.json', import.meta.url), 'utf8'))
const specs = (Array.isArray(raw) ? raw : [raw]).map(spec => ({
  ...spec,
  packageName: manifest.name,
  packageVersion: manifest.version,
}))

runPluginCli(specs, process.argv.slice(2), packageRoot).then(
  code => { process.exitCode = code },
  error => {
    process.stderr.write(\`\${manifest.name}: \${error instanceof Error ? error.message : String(error)}\\n\`)
    process.exitCode = 1
  },
)
`

for (const item of packages) {
  const directory = fileURLToPath(new URL(`plugins/${item.dir}/`, root))
  await mkdir(join(directory, 'bin'), { recursive: true })
  const name = `@pirate-608/dsh-${item.slug}`
  const manifest = {
    name,
    version: '0.1.0',
    description: item.description,
    type: 'module',
    private: item.private || undefined,
    bin: { [`dsh-${item.slug}`]: './bin/cli.js' },
    exports: { './package.json': './package.json', './cordis.patch.yml': './cordis.patch.yml' },
    files: ['bin', 'preset.json', 'skills', 'scripts', 'vendor', 'runtime', 'fallback', 'mcp-server', 'autocad-plugin', 'assets', 'README*', 'LICENSE*', 'NOTICE*', 'UPSTREAM*', 'cordis.patch.yml'],
    publishConfig: item.private ? undefined : { access: 'public' },
    license: item.license,
    engines: { node: '^22.19.0 || >=24.0.0' },
    peerDependencies: { '@deepseek-ai/dsh': '>=0.0.1-rc.5 <0.2.0' },
    peerDependenciesMeta: { '@deepseek-ai/dsh': { optional: true } },
    dependencies: { '@pirate-608/dsh-plugin-kit': 'workspace:^' },
    devDependencies: { '@deepseek-ai/dsh': '0.1.0-rc.8' },
    dsh: { bundle: { patch: './cordis.patch.yml' } },
    scripts: {
      build: 'node --check bin/cli.js',
      typecheck: 'node --check bin/cli.js',
      test: 'node --check bin/cli.js',
      prepack: 'pnpm run build && pnpm run test',
    },
  }
  await writeFile(join(directory, 'package.json'), `${JSON.stringify(manifest, undefined, 2)}\n`)
  const presetDocument = Array.isArray(item.preset)
    ? item.preset.map(spec => ({ ...spec, commandName: `dsh-${item.slug}` }))
    : { ...item.preset, commandName: `dsh-${item.slug}` }
  await writeFile(join(directory, 'preset.json'), `${JSON.stringify(presetDocument, undefined, 2)}\n`)
  await writeFile(join(directory, 'bin', 'cli.js'), bin)
  await writeFile(join(directory, 'cordis.patch.yml'), '[]\n')
  const presetIds = (Array.isArray(item.preset) ? item.preset : [item.preset]).map(spec => spec.id)
  await prependReadme(directory, 'README.md', `# ${name}\n\n${item.description}.\n\nInstall into a DSH profile, then create the dedicated preset:\n\n\`\`\`sh\ndsh plugin --profile web add ${name}\ndsh plugin --profile web exec dsh-${item.slug} preset install\ndsh plugin --profile web exec dsh-${item.slug} doctor\n\`\`\`\n\nManaged preset id${presetIds.length === 1 ? '' : 's'}: ${presetIds.map(id => `\`${id}\``).join(', ')}. The standard preset does not receive this package's tools or skills. MCP writes and unknown tools require one-shot approval.\n\n${item.private ? '**Publication blocked:** this package remains private until its first-party license is resolved.\n' : ''}`)
  await prependReadme(directory, 'README.zh-CN.md', `# ${name}\n\n${item.description}。\n\n先安装到 DSH profile，再创建独立 Preset：\n\n\`\`\`powershell\ndsh plugin --profile web add ${name}\ndsh plugin --profile web exec dsh-${item.slug} preset install\ndsh plugin --profile web exec dsh-${item.slug} doctor\n\`\`\`\n\n受管 Preset：${presetIds.map(id => `\`${id}\``).join('、')}。标准 Preset 不会得到本包的工具或技能；MCP 写操作和未知工具必须经过一次性审批。\n\n${item.private ? '**禁止发布：**补齐作者代码许可证之前，本包保持 private。\n' : ''}`)
}

function fileURLToPath(url) {
  return decodeURIComponent(url.pathname.replace(/^\/(?:[A-Za-z]:)/, value => value.slice(1))).replaceAll('/', '\\')
}

async function prependReadme(directory, name, header) {
  const path = join(directory, name)
  let existing = ''
  try { existing = await readFile(path, 'utf8') } catch (error) { if (error?.code !== 'ENOENT') throw error }
  const start = '<!-- dsh-package-header -->'
  const end = '<!-- /dsh-package-header -->'
  const block = `${start}\n${header.trim()}\n${end}`
  const pattern = /<!-- dsh-package-header -->[\s\S]*?<!-- \/dsh-package-header -->/
  const output = pattern.test(existing) ? existing.replace(pattern, block) : `${block}\n\n${existing}`
  await writeFile(path, output.trimEnd() + '\n')
}
