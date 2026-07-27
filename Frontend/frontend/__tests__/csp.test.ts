import fs from 'fs'
import path from 'path'
import { describe, it, expect, vi } from 'vitest'

// csp.ts modül tepesinde electron'u import ediyor; jsdom ortamında böyle bir
// modül yok. Politika üretimi saf bir fonksiyon olduğu için mock yeterli.
vi.mock('electron', () => ({
  app: { on: vi.fn() },
  session: { defaultSession: { webRequest: { onHeadersReceived: vi.fn() } } },
}))

import { buildPolicy, MONACO_CDN_PREFIX } from '../main/helpers/csp'

const directive = (policy: string, name: string): string => {
  const found = policy
    .split(';')
    .map((part) => part.trim())
    .find((part) => part === name || part.startsWith(`${name} `))
  if (!found) throw new Error(`'${name}' direktifi politikada yok: ${policy}`)
  return found
}

describe('CSP — Monaco CDN sabiti', () => {
  /**
   * Bu testin varlık sebebi: CSP'deki jsdelivr izni sürüm SEGMENTİNE kadar
   * sabitlenmiş durumda. `@monaco-editor/loader` yükseltildiğinde yeni sürüm
   * bu önekle eşleşmez ve editör sahada SESSİZCE ölür — kullanıcı yalnızca boş
   * bir editör görür, sebebi ise yalnızca konsolda yazar.
   *
   * Hatırlamaya bağlı bir kural ateşlenmiyor; o yüzden ayrışma bir teste
   * bağlandı. Bu test kırıldıysa yapılacak iş: csp.ts'deki MONACO_CDN sabitini
   * loader'ın yeni varsayılanıyla güncellemek (ya da monaco'yu yerelden
   * servis edip jsdelivr iznini tamamen kaldırmak).
   */
  it('loader varsayılanıyla aynı sürüme işaret eder', () => {
    const configPath = path.resolve(
      process.cwd(),
      'node_modules/@monaco-editor/loader/lib/es/config/index.js'
    )
    const source = fs.readFileSync(configPath, 'utf-8')
    const match = source.match(/vs:\s*['"]([^'"]+)['"]/)
    expect(match, 'loader config içinde vs yolu bulunamadı').toBeTruthy()

    // CSP yol öneki eşleştirmesi için sondaki '/' şart; loader onsuz yazıyor.
    expect(MONACO_CDN_PREFIX).toBe(`${match![1]}/`)
  })

  it('çıplak host değil, yola sabitlenmiş bir önektir', () => {
    // Çıplak `https://cdn.jsdelivr.net` jsdelivr'daki her npm paketini
    // script-src'ye sokardı — CSP'nin kapatmaya çalıştığı deliğin kendisi.
    expect(MONACO_CDN_PREFIX).toMatch(/^https:\/\/cdn\.jsdelivr\.net\/npm\/monaco-editor@[^/]+\/min\/vs\/$/)
  })
})

describe('CSP — prod politikası', () => {
  const policy = buildPolicy(true)

  it("script-src'de 'unsafe-eval' ya da 'unsafe-inline' YOKTUR", () => {
    // Dev gevşekliğinin prod'a sızması, politikanın kod-yükleme tarafını
    // tümüyle anlamsızlaştırır. Kapı burada.
    const scriptSrc = directive(policy, 'script-src')
    expect(scriptSrc).not.toContain("'unsafe-eval'")
    expect(scriptSrc).not.toContain("'unsafe-inline'")
  })

  it('websocket kaynağı içermez', () => {
    expect(policy).not.toContain('ws://')
    expect(policy).not.toContain('wss://')
  })

  it('ölçülmüş zorunlu kaynakları içerir', () => {
    expect(directive(policy, 'script-src')).toContain(MONACO_CDN_PREFIX)
    // Monaco dil worker'ı blob: üzerinden kuruluyor.
    expect(directive(policy, 'worker-src')).toContain('blob:')
    // Monaco codicon ikon fontu bir data: URI.
    expect(directive(policy, 'font-src')).toContain('data:')
    // Sohbet ekleri FileReader.readAsDataURL ile data: URI olarak render ediliyor.
    expect(directive(policy, 'img-src')).toContain('data:')
    // Backend dinamik portta dinliyor.
    expect(directive(policy, 'connect-src')).toContain('http://127.0.0.1:*')
  })

  it('tehlikeli yüzeyleri kapatır', () => {
    expect(directive(policy, 'object-src')).toBe("object-src 'none'")
    expect(directive(policy, 'base-uri')).toBe("base-uri 'none'")
    expect(directive(policy, 'frame-src')).toBe("frame-src 'none'")
    expect(directive(policy, 'frame-ancestors')).toBe("frame-ancestors 'none'")
    // 'none' değil 'self': giriş formu preventDefault çağırmıyor, gerçek bir
    // form gezinmesi olabiliyor. Asıl tehdit uzak endpoint'e POST — o kapalı.
    expect(directive(policy, 'form-action')).toBe("form-action 'self'")
  })

  it('uzak origin izinleri yalnızca ölçülmüş olanlardır', () => {
    const remoteHosts = policy.match(/https:\/\/[^\s;]+/g) ?? []
    const allowed = new Set([
      MONACO_CDN_PREFIX,
      'https://fonts.googleapis.com',
      'https://fonts.gstatic.com',
      'https://images.unsplash.com',
    ])
    for (const host of remoteHosts) {
      expect(allowed.has(host), `politikada beklenmeyen uzak kaynak: ${host}`).toBe(true)
    }
  })
})

describe('CSP — dev politikası', () => {
  const policy = buildPolicy(false)

  it('HMR için eval, satır içi script ve websocket izni verir', () => {
    const scriptSrc = directive(policy, 'script-src')
    expect(scriptSrc).toContain("'unsafe-eval'")
    expect(scriptSrc).toContain("'unsafe-inline'")
    const connectSrc = directive(policy, 'connect-src')
    expect(connectSrc).toContain('ws://127.0.0.1:*')
    expect(connectSrc).toContain('ws://localhost:*')
  })

  it('gevşeme yalnızca script-src ve connect-src ile sınırlıdır', () => {
    // Dev ile prod arasındaki farkın kapsamı bilinçli olarak dar; başka bir
    // direktifin dallanması fark edilmeden politikayı aşındırırdı.
    const prod = buildPolicy(true)
    const asMap = (p: string) =>
      Object.fromEntries(
        p.split(';').map((part) => {
          const [name, ...rest] = part.trim().split(' ')
          return [name, rest.join(' ')]
        })
      )
    const devMap = asMap(policy)
    const prodMap = asMap(prod)
    const differing = Object.keys(prodMap).filter((k) => devMap[k] !== prodMap[k])
    expect(differing.sort()).toEqual(['connect-src', 'script-src'])
  })
})
