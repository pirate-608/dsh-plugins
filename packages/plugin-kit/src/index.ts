/** Public API for managed pirate-608 DSH plugins. */

export { packageRootFrom, resolvePresetContext, runPluginCli } from './cli.js'
export { installPreset, presetStatus, removePreset, renderRows, updatePreset } from './preset.js'
export type {
  DoctorProbe,
  McpPolicySpec,
  McpServerSpec,
  PresetContext,
  PresetSpec,
  PresetStatus,
  PresetWriteResult,
  RuntimeCommand,
} from './types.js'
