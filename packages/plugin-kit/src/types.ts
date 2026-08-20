/** One stdio MCP service mounted inside a generated agent preset. */
export interface McpServerSpec {
  id: string
  serverName: string
  command: string
  args?: readonly string[]
  env?: Readonly<Record<string, string>>
  cwd?: string
  toolCallTimeoutMs?: number
  failOnStartupError?: boolean
}

/** Fail-closed policy for MCP tools in one preset. */
export interface McpPolicySpec {
  serverNames: readonly string[]
  readOnly?: readonly string[]
  ask?: readonly string[]
  deny?: readonly string[]
}

/** One executable prerequisite inspected by the package doctor command. */
export interface DoctorProbe {
  label: string
  command: string
  args?: readonly string[]
  optional?: boolean
}

/** Explicit package-local runtime management command; never run during installation. */
export interface RuntimeCommand {
  command: string
  args?: readonly string[]
  cwd?: string
}

/** Declarative definition of one managed, standard-derived agent preset. */
export interface PresetSpec {
  packageName: string
  packageVersion: string
  commandName?: string
  id: string
  name: string
  description: string
  providerName: string
  skillsDir?: string
  mcpServers?: readonly McpServerSpec[]
  policy?: McpPolicySpec
  platform?: NodeJS.Platform
  doctor?: readonly DoctorProbe[]
  runtime?: Partial<Record<'install' | 'status' | 'remove', RuntimeCommand>>
}

/** Resolved host and package paths used by lifecycle operations. */
export interface PresetContext {
  dshHome: string
  profileName: string
  profileDir: string
  standardPresetDir: string
  packageRoot: string
  mcpClientPlugin: string
  skillFilesystemPlugin: string
  policyPlugin: string
  dshVersion: string
}

/** Managed preset state exposed by status. */
export interface PresetStatus {
  kind: 'absent' | 'clean' | 'outdated' | 'modified' | 'invalid'
  presetDir: string
  message: string
}

/** Result of an install or update operation. */
export interface PresetWriteResult {
  presetDir: string
  backupDir?: string
}
