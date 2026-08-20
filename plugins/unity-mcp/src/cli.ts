#!/usr/bin/env node

/** Command-line entry for the managed Unity preset. */

import { fileURLToPath } from 'node:url'
import { runPluginCli } from '@pirate-608/dsh-plugin-kit'
import { UNITY_PRESET } from './spec.js'

const packageRoot = fileURLToPath(new URL('../', import.meta.url))
runPluginCli(UNITY_PRESET, process.argv.slice(2), packageRoot).then(
  code => { process.exitCode = code },
  error => {
    process.stderr.write(`dsh-unity-mcp: ${error instanceof Error ? error.message : String(error)}\n`)
    process.exitCode = 1
  },
)
