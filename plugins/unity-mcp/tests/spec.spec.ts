import { describe, expect, it } from 'vitest'
import { UNITY_PRESET } from '../src/spec.js'

describe('Unity preset spec', () => {
  it('pins the server and scopes tools behind the shared policy', () => {
    expect(UNITY_PRESET.id).toBe('unity')
    expect(UNITY_PRESET.mcpServers?.[0]?.args).toContain('mcpforunityserver==10.1.2')
    expect(UNITY_PRESET.policy?.serverNames).toEqual(['unity'])
    expect(UNITY_PRESET.providerName).toBe('unity-skills')
  })
})
