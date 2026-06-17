import { describe, it, expect } from 'vitest'
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

  for (const ch of fileChannels) {
    it(`dosya kanalı geçer: ${ch}`, () => {
      expect(() => assertAllowedInvokeChannel(ch)).not.toThrow()
    })
  }

  it('app-token-get kanalı geçer', () => {
    expect(() => assertAllowedInvokeChannel('app-token-get')).not.toThrow()
  })
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
    'session-get',
    'session-set',
    'session-clear',
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
  it('tam olarak 22 kanal içerir', () => {
    expect(ALLOWED_INVOKE_CHANNELS.size).toBe(22)
  })

  it('her kanal benzersiz', () => {
    const arr = [...ALLOWED_INVOKE_CHANNELS]
    expect(arr.length).toBe(new Set(arr).size)
  })

  it('dosya kanallarının hepsi whitelist\'te', () => {
    const expected = ['get-backend-base-url', 'open-file-dialog', 'open-folder-dialog', 'read-directory',
      'read-file', 'write-file', 'file-exists', 'write-multiple-files',
      'create-file', 'create-folder', 'rename-entry', 'delete-entry', 'move-entry',
      'save-file-dialog', 'export-text-file', 'import-text-file', 'delete-file']
    for (const ch of expected) {
      expect(ALLOWED_INVOKE_CHANNELS.has(ch)).toBe(true)
    }
  })

  it('app-token-get kanalı whitelist\'te', () => {
    expect(ALLOWED_INVOKE_CHANNELS.has('app-token-get')).toBe(true)
  })

  it('path-exists kanalı whitelist\'te', () => {
    expect(ALLOWED_INVOKE_CHANNELS.has('path-exists')).toBe(true)
  })

  it('terminal kanalları whitelist\'te', () => {
    for (const ch of ['terminal-spawn', 'terminal-write', 'terminal-resize']) {
      expect(ALLOWED_INVOKE_CHANNELS.has(ch)).toBe(true)
    }
  })
})
