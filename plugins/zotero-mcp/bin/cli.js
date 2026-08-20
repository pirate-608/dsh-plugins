#!/usr/bin/env node
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
    process.stderr.write(`${manifest.name}: ${error instanceof Error ? error.message : String(error)}\n`)
    process.exitCode = 1
  },
)
