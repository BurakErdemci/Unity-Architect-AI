/**
 * `/usage` ve `/context` raporlarının SOHBETE YAZMADAN gösterilmesi.
 *
 * Neden var: bu iki rapora bugüne kadar ancak sohbete `/usage` yazarak
 * bakılabiliyordu — her bakış geçmişe bir mesaj çifti bırakıyordu ve akış
 * sürerken bakmak mümkün değildi (Burak'ın 30 Ağu 2026 talebi: "chat akarken
 * bu verileri görebilmek").
 *
 * Testlerin sabitlediği asıl şey DÖRT AYRI "veri yok" hâlinin birbirine
 * karışmaması:
 *   oturum yok · tur akıyor · bu sağlayıcıda yok · hata
 * Hepsini tek boş kutuya çevirmek, kullanıcıya "bozuk" ile "henüz değil"i
 * aynı şey gibi gösterirdi — ve ikisinin yapılacak işi farklı.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

import { SessionReportPanel } from '../renderer/components/home/SessionReportPanel'

afterEach(() => cleanup())

const CONTEXT_METNI = [
  '**Model:** claude-opus-5',
  '',
  '**Tokens:** 69.9k / 1m (7%)',
].join('\n')

const cevapla = (esleme: Record<string, any>) => {
  const f = vi.fn(async (url: string) => {
    const kind = url.endsWith('/context') ? 'context' : 'usage'
    const d = esleme[kind] ?? { status: 'no_session' }
    return { ok: true, json: async () => d } as any
  })
  ;(globalThis as any).fetch = f
  return f
}

const ciz = (props: Partial<React.ComponentProps<typeof SessionReportPanel>> = {}) =>
  render(
    <SessionReportPanel
      open
      onClose={() => {}}
      API="http://x"
      sessionToken="t"
      convId={7}
      {...props}
    />,
  )

beforeEach(() => { vi.restoreAllMocks() })

describe('dört ayrı boşluk hâli', () => {
  it('oturum yokken bunu SÖYLÜYOR', async () => {
    cevapla({ usage: { status: 'no_session' }, context: { status: 'no_session' } })
    ciz()
    await waitFor(() => expect(screen.getAllByTestId('report-empty-no_session').length).toBe(2))
  })

  it('tur akarken "meşgul" diyor, "veri yok" demiyor', async () => {
    cevapla({ usage: { status: 'busy' }, context: { status: 'busy' } })
    ciz()
    await waitFor(() => expect(screen.getAllByTestId('report-empty-busy').length).toBe(2))
    expect(screen.queryByTestId('report-empty-no_session')).toBeNull()
  })

  it('sağlayıcı desteklemiyorsa bunu ayrıca söylüyor', async () => {
    // Codex'te /context yok — bu bir arıza değil, bir yokluk.
    cevapla({ usage: { status: 'ok', text: '50% used' }, context: { status: 'unsupported' } })
    ciz()
    await waitFor(() => expect(screen.getByTestId('report-empty-unsupported')).toBeTruthy())
  })

  it('sunucu bu ucu tanımıyorsa "yeniden başlat" diyor, "hata" demiyor', async () => {
    // 404 = çalışan arka uç bu sürümden eski. Yapılacak şey tek ve belli;
    // "Ayrıntı sunucu loglarında" demek kullanıcıyı boşuna log okumaya yollar.
    ;(globalThis as any).fetch = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }) as any)
    ciz()
    await waitFor(() => expect(screen.getAllByTestId('report-empty-outdated').length).toBe(2))
    expect(screen.queryByTestId('report-empty-error')).toBeNull()
  })

  it('hata ayrı bir hâl', async () => {
    cevapla({ usage: { status: 'error' }, context: { status: 'error' } })
    ciz()
    await waitFor(() => expect(screen.getAllByTestId('report-empty-error').length).toBe(2))
  })
})

describe('rapor geldiğinde', () => {
  it('bağlam kartı gerçek sayıyı çiziyor', async () => {
    cevapla({ usage: { status: 'no_session' }, context: { status: 'ok', text: CONTEXT_METNI } })
    ciz()
    await waitFor(() => expect(screen.getByText('69.9k / 1m token')).toBeTruthy())
  })

  it('gerçek bağlam metni DIŞARIYA da bildiriliyor — gösterge onu kullanacak', async () => {
    const haber = vi.fn()
    cevapla({ usage: { status: 'no_session' }, context: { status: 'ok', text: CONTEXT_METNI } })
    ciz({ onContextText: haber })
    await waitFor(() => expect(haber).toHaveBeenCalledWith(CONTEXT_METNI))
  })

  it('bildirim YALNIZ gerçekten rapor geldiğinde gidiyor', async () => {
    const haber = vi.fn()
    cevapla({ usage: { status: 'busy' }, context: { status: 'busy' } })
    ciz({ onContextText: haber })
    await waitFor(() => expect(screen.getAllByTestId('report-empty-busy').length).toBe(2))
    expect(haber).not.toHaveBeenCalled()
  })
})

describe('yenileme', () => {
  it('yenile düğmesi gerçekten yeniden çekiyor', async () => {
    const f = cevapla({ usage: { status: 'busy' }, context: { status: 'busy' } })
    ciz()
    await waitFor(() => expect(f).toHaveBeenCalledTimes(2))
    fireEvent.click(screen.getByTestId('report-refresh'))
    await waitFor(() => expect(f).toHaveBeenCalledTimes(4))
  })

  it('panel kapalıyken hiç istek atmıyor', () => {
    const f = cevapla({})
    ciz({ open: false })
    expect(f).not.toHaveBeenCalled()
    expect(screen.queryByTestId('session-report-panel')).toBeNull()
  })
})
