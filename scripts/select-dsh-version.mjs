/** Rewrite development-only DSH dependencies for compatibility-matrix jobs. */

import { readFile, readdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const requested = process.argv[2]
if (!['0.0.1-rc.5', '0.1.0-rc.6', '0.1.0-rc.8'].includes(requested)) {
  throw new Error('usage: node scripts/select-dsh-version.mjs <0.0.1-rc.5|0.1.0-rc.6|0.1.0-rc.8>')
}

const roots = ['.']
for (const root of roots) await visit(root)

async function visit(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === 'lib' || entry.name === 'vendor') continue
    const path = join(directory, entry.name)
    if (entry.isDirectory()) { await visit(path); continue }
    if (entry.name !== 'package.json') continue
    const manifest = JSON.parse(await readFile(path, 'utf8'))
    let changed = false
    for (const section of ['devDependencies']) {
      for (const name of Object.keys(manifest[section] ?? {})) {
        if (name === '@deepseek-ai/dsh' || name.startsWith('@deepseek-ai/dsh-')) {
          manifest[section][name] = requested
          changed = true
        }
      }
    }
    if (changed) await writeFile(path, `${JSON.stringify(manifest, undefined, 2)}\n`)
  }
}
