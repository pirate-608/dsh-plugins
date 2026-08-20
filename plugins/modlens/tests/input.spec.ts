import { describe, expect, it } from 'vitest'
import { loadImage, sniff } from '../src/input.js'

describe('image admission', () => {
  it('accepts known magic bytes and rejects arbitrary data', () => {
    expect(sniff(Uint8Array.of(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a))).toBe('image/png')
    expect(() => sniff(Uint8Array.of(1, 2, 3))).toThrow(/recognized/)
  })

  it('rejects loopback remote URLs before fetching', async () => {
    const ctx = {
      fs: { resolve: async () => ({}), readBytes: async () => new Uint8Array() },
      attachments: { readImage: async () => ({ ref: { mediaType: 'image/png' }, data: new Uint8Array() }) },
    }
    await expect(loadImage(ctx, { url: 'http://127.0.0.1/private.png' }, {
      signal: new AbortController().signal,
    }, 1024)).rejects.toThrow(/private or local/)
  })
})
