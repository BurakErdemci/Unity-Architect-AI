import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import fs from 'fs'
import path from 'path'
import os from 'os'
import { sessionGet, sessionSet, sessionClear, SafeStorageAdapter } from '../main/helpers/session-storage-handlers'

// Gerçek geçici dizin kullan — fs mock'lamaya gerek yok
let tmpDir: string

function makeDeps(adapter: Partial<SafeStorageAdapter> = {}): { userDataPath: string; safeStorage: SafeStorageAdapter } {
  return {
    userDataPath: tmpDir,
    safeStorage: {
      isEncryptionAvailable: () => true,
      encryptString: (s) => Buffer.from(s + ':encrypted'),
      decryptString: (b) => b.toString().replace(':encrypted', ''),
      ...adapter,
    },
  }
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'unity-session-test-'))
})

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true })
})

describe('sessionGet', () => {
  it('session dosyası yokken null döner', async () => {
    const result = await sessionGet(makeDeps())
    expect(result).toBeNull()
  })

  it('şifreleme kullanılamıyorsa null döner', async () => {
    // Önce dosyayı oluştur
    await sessionSet(makeDeps(), 'test-token')
    // Şimdi şifreleme kapalıyken get dene
    const result = await sessionGet(makeDeps({ isEncryptionAvailable: () => false }))
    expect(result).toBeNull()
  })

  it('set sonrası get token\'ı geri döndürür (round-trip)', async () => {
    const deps = makeDeps()
    await sessionSet(deps, 'my-secret-token')
    const result = await sessionGet(deps)
    expect(result).toBe('my-secret-token')
  })

  it('özel karakterler içeren token\'ı doğru saklar', async () => {
    const token = 'tok_abc123!@#$%^&*()-_=+[]{}|;:,.<>?'
    const deps = makeDeps()
    await sessionSet(deps, token)
    const result = await sessionGet(deps)
    expect(result).toBe(token)
  })

  it('bozuk dosya içeriğinde hata fırlatmaz, null döner', async () => {
    const file = path.join(tmpDir, 'session.enc')
    fs.writeFileSync(file, Buffer.from([0x00, 0xff, 0xfe]))  // geçersiz içerik
    const deps = makeDeps({
      decryptString: () => { throw new Error('decrypt failed') },
    })
    const result = await sessionGet(deps)
    expect(result).toBeNull()
  })
})

describe('sessionSet', () => {
  it('şifreleme kullanılamıyorsa false döner', async () => {
    const result = await sessionSet(makeDeps({ isEncryptionAvailable: () => false }), 'token')
    expect(result).toBe(false)
  })

  it('başarıyla yazarsa true döner', async () => {
    const result = await sessionSet(makeDeps(), 'token')
    expect(result).toBe(true)
  })

  it('session.enc dosyasını oluşturur', async () => {
    await sessionSet(makeDeps(), 'token')
    expect(fs.existsSync(path.join(tmpDir, 'session.enc'))).toBe(true)
  })

  it('ikinci set çağrısı önceki token\'ın üzerine yazar', async () => {
    const deps = makeDeps()
    await sessionSet(deps, 'old-token')
    await sessionSet(deps, 'new-token')
    const result = await sessionGet(deps)
    expect(result).toBe('new-token')
  })

  it('encryptString hatası fırlatırsa false döner', async () => {
    const result = await sessionSet(
      makeDeps({ encryptString: () => { throw new Error('encrypt failed') } }),
      'token'
    )
    expect(result).toBe(false)
  })
})

describe('sessionClear', () => {
  it('dosya yokken true döner (hata fırlatmaz)', async () => {
    const result = await sessionClear(makeDeps())
    expect(result).toBe(true)
  })

  it('mevcut dosyayı siler', async () => {
    const deps = makeDeps()
    await sessionSet(deps, 'token')
    expect(fs.existsSync(path.join(tmpDir, 'session.enc'))).toBe(true)

    await sessionClear(deps)
    expect(fs.existsSync(path.join(tmpDir, 'session.enc'))).toBe(false)
  })

  it('clear sonrası get null döner', async () => {
    const deps = makeDeps()
    await sessionSet(deps, 'token')
    await sessionClear(deps)
    const result = await sessionGet(deps)
    expect(result).toBeNull()
  })

  it('set → clear → set yeniden çalışır', async () => {
    const deps = makeDeps()
    await sessionSet(deps, 'first')
    await sessionClear(deps)
    await sessionSet(deps, 'second')
    const result = await sessionGet(deps)
    expect(result).toBe('second')
  })
})

describe('Session tam akış', () => {
  it('login → restore → logout akışı', async () => {
    const deps = makeDeps()

    // Login: token kaydet
    const setResult = await sessionSet(deps, 'session-abc-123')
    expect(setResult).toBe(true)

    // Uygulama yeniden açılır: token restore
    const restored = await sessionGet(deps)
    expect(restored).toBe('session-abc-123')

    // Logout: token temizle
    const clearResult = await sessionClear(deps)
    expect(clearResult).toBe(true)

    // Sonraki açılışta session yok
    const afterLogout = await sessionGet(deps)
    expect(afterLogout).toBeNull()
  })

  it('"Beni hatırla" kapalıyken token saklanmaz', async () => {
    const deps = makeDeps()
    // persistSession=false → sessionClear çağrılır, set çağrılmaz
    await sessionClear(deps)   // logout/no-persist path
    const result = await sessionGet(deps)
    expect(result).toBeNull()
  })
})
