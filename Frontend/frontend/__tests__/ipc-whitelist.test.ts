import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  ALLOWED_INVOKE_CHANNELS,
  assertAllowedInvokeChannel,
} from '../main/helpers/ipc-whitelist'

describe('IPC Whitelist — izinli kanallar', () => {
  const fileChannels = [
    'get-backend-base-url',
    'open-file-dialog',
    'open-folder-dialog',
    'read-directory',
    'read-file',
    'write-file',
    'file-exists',
    'write-multiple-files',
  ]

  const sessionChannels = [
    'session-get',
    'session-set',
    'session-clear',
  ]

  for (const ch of fileChannels) {
    it(`dosya kanalı geçer: ${ch}`, () => {
      expect(() => assertAllowedInvokeChannel(ch)).not.toThrow()
    })
  }

  for (const ch of sessionChannels) {
    it(`session kanalı geçer: ${ch}`, () => {
      expect(() => assertAllowedInvokeChannel(ch)).not.toThrow()
    })
  }
})

describe('IPC Whitelist — izinsiz kanallar engellenir', () => {
  const blockedChannels = [
    'exec',
    'shell',
    'eval',
    '../../../etc/passwd',
    'read-file; rm -rf /',
    'session-get\0malicious',
    '',
    'OPEN-FILE-DIALOG',          // büyük harf farkı
    'open_file_dialog',          // alt çizgi
    'write-file-extra',          // prefix match değil, tam eşleşme
    'session',
    'get',
    'node:fs',
  ]

  for (const ch of blockedChannels) {
    it(`engellenir: "${ch}"`, () => {
      expect(() => assertAllowedInvokeChannel(ch)).toThrow('IPC channel izinsiz')
    })
  }
})

describe('IPC Whitelist — Set doğruluğu', () => {
  it('tam olarak 10 kanal içerir', () => {
    expect(ALLOWED_INVOKE_CHANNELS.size).toBe(11)
  })

  it('her kanal benzersiz', () => {
    const arr = [...ALLOWED_INVOKE_CHANNELS]
    expect(arr.length).toBe(new Set(arr).size)
  })

  it('dosya kanallarının hepsi whitelist\'te', () => {
    const expected = ['get-backend-base-url', 'open-file-dialog', 'open-folder-dialog', 'read-directory',
      'read-file', 'write-file', 'file-exists', 'write-multiple-files']
    for (const ch of expected) {
      expect(ALLOWED_INVOKE_CHANNELS.has(ch)).toBe(true)
    }
  })

  it('session kanallarının hepsi whitelist\'te', () => {
    const expected = ['session-get', 'session-set', 'session-clear']
    for (const ch of expected) {
      expect(ALLOWED_INVOKE_CHANNELS.has(ch)).toBe(true)
    }
  })
})
