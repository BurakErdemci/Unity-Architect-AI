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
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react'

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

describe('başarılı ama BOŞ rapor', () => {
  it('HTTP 200 + status ok + boş metin, HATA diye gösterilmiyor', async () => {
    // Denetim bulgusu (30 Ağu 2026): panel `r.text`in doğruluğuna bakıp boş
    // metni `bos()`a yolluyordu ve orada hiçbir dal eşleşmediği için sondaki
    // varsayılan seçiliyordu — `report.error`. Yani sunucu doğru çalışmışken
    // kullanıcıya "Rapor alınamadı, ayrıntı sunucu loglarında" deniyordu; oysa
    // okunacak bir log bile yok. Sunucuyu, başarıyla verdiği bir cevap için
    // suçlamak, kullanıcıyı olmayan bir arızayı aramaya yollar.
    cevapla({ usage: { status: 'ok', text: '' }, context: { status: 'ok', text: '' } })
    ciz()
    await waitFor(() => expect(screen.getAllByTestId('report-empty-ok').length).toBe(2))
    expect(screen.queryByTestId('report-empty-error')).toBeNull()
    expect(screen.getByTestId('session-report-panel').textContent || '')
      .not.toContain('Rapor alınamadı')
  })

  it('boş başarı, "oturum yok" ile de karıştırılmıyor', async () => {
    // Beş ayrı boşluk hâlinin hepsi ayrı bir sonraki adım anlatıyor; ikisini
    // birleştirmek kullanıcıya yanlış işi yaptırır.
    cevapla({ usage: { status: 'ok', text: '' }, context: { status: 'ok', text: '' } })
    ciz()
    await waitFor(() => expect(screen.getAllByTestId('report-empty-ok').length).toBe(2))
    expect(screen.queryByTestId('report-empty-no_session')).toBeNull()
  })

  it('dolu bir rapor hâlâ KART olarak çiziliyor — boş hâl onu yutmuyor', async () => {
    cevapla({ usage: { status: 'no_session' }, context: { status: 'ok', text: CONTEXT_METNI } })
    ciz()
    await waitFor(() => expect(screen.getByText('69.9k / 1m token')).toBeTruthy())
    expect(screen.queryByTestId('report-empty-ok')).toBeNull()
  })
})

describe('sohbet değişince gelen BAYAT yanıt', () => {
  /** Elde tutulan `fetch`: her çağrı bir söz döndürüyor, çözümü testte. */
  const tutulanFetch = () => {
    const bekleyen: { url: string; resolve: (v: any) => void }[] = []
    ;(globalThis as any).fetch = vi.fn(
      (url: string) => new Promise(resolve => { bekleyen.push({ url, resolve }) }),
    )
    return bekleyen
  }
  const yanit = (text: string) => ({ ok: true, status: 200, json: async () => ({ status: 'ok', text }) })

  it('A sohbetinin geç yanıtı, AÇIK olan B panelini EZMİYOR', async () => {
    // Denetim bulgusu (30 Ağu 2026): her `Promise.all` sonucu aynı state'e
    // koşulsuz yazılıyordu. Kullanıcı A için paneli açıp kapatıyor, B için
    // yeniden açıyor; B'nin raporu çiziliyor, sonra A'nın yavaş yanıtı gelip
    // onu eziyordu. Panelde hangi sohbete ait olduğu HİÇBİR YERDE yazmadığı
    // için kullanıcı yanlış raporu doğru sanarak okuyor.
    const bekleyen = tutulanFetch()
    const view = ciz()                                        // A (convId 7) → 2 istek
    view.rerender(
      <SessionReportPanel open={false} onClose={() => {}} API="http://x" sessionToken="t" convId={7} />,
    )
    view.rerender(
      <SessionReportPanel open onClose={() => {}} API="http://x" sessionToken="t" convId={8} />,
    )
    // Kapı: dört istek gerçekten uçuşta değilse aşağıdaki yarış hiç kurulmamış
    // olur ve test kendi ölçtüğü şeyi ölçemeden yeşil yanar.
    await waitFor(() => expect(bekleyen.length).toBe(4))

    await act(async () => {
      bekleyen[2].resolve(yanit('YENI_KULLANIM'))
      bekleyen[3].resolve(yanit('**Tokens:** 2 / 10 (20%)'))
    })
    expect(screen.getByTestId('session-report-panel').textContent).toContain('YENI_KULLANIM')

    await act(async () => {
      bekleyen[0].resolve(yanit('ESKI_KULLANIM'))
      bekleyen[1].resolve(yanit('**Tokens:** 1 / 10 (10%)'))
    })
    const metin = screen.getByTestId('session-report-panel').textContent || ''
    expect(metin).not.toContain('ESKI_KULLANIM')
    expect(metin).not.toContain('1 / 10 token')
    expect(metin).toContain('YENI_KULLANIM')
  })

  it('aynı sohbette arka arkaya yenilemede de son çekim kazanıyor', async () => {
    // Kimlik testi `convId` üzerinden yapılsaydı bu senaryo KAÇARDI: iki çekim
    // de aynı sohbete ait ve yine de biri bayat. Sayaç bu yüzden seçildi.
    const bekleyen = tutulanFetch()
    ciz()
    await waitFor(() => expect(bekleyen.length).toBe(2))
    fireEvent.click(screen.getByTestId('report-refresh'))
    await waitFor(() => expect(bekleyen.length).toBe(4))

    await act(async () => {
      bekleyen[2].resolve(yanit('IKINCI'))
      bekleyen[3].resolve(yanit('**Tokens:** 2 / 10 (20%)'))
    })
    await act(async () => {
      bekleyen[0].resolve(yanit('BIRINCI'))
      bekleyen[1].resolve(yanit('**Tokens:** 1 / 10 (10%)'))
    })
    const metin = screen.getByTestId('session-report-panel').textContent || ''
    expect(metin).toContain('IKINCI')
    expect(metin).not.toContain('BIRINCI')
  })

  it('bayat yanıt DIŞARIYA da bildirilmiyor — gösterge yanlış sayıyı almasın', async () => {
    // `onContextText` göstergeye gerçek doluluğu taşıyor. Bayat bir bağlam
    // metnini oraya sızdırmak, arızayı panelden göstergeye taşımak olurdu.
    const haber = vi.fn()
    const bekleyen = tutulanFetch()
    const view = render(
      <SessionReportPanel open onClose={() => {}} API="http://x" sessionToken="t" convId={7} onContextText={haber} />,
    )
    view.rerender(
      <SessionReportPanel open onClose={() => {}} API="http://x" sessionToken="t" convId={8} onContextText={haber} />,
    )
    await waitFor(() => expect(bekleyen.length).toBe(4))
    await act(async () => {
      bekleyen[2].resolve(yanit('YENI'))
      bekleyen[3].resolve(yanit(CONTEXT_METNI))
    })
    await act(async () => {
      bekleyen[0].resolve(yanit('ESKI'))
      bekleyen[1].resolve(yanit('**Tokens:** 1 / 10 (10%)'))
    })
    expect(haber).toHaveBeenCalledTimes(1)
    expect(haber).toHaveBeenCalledWith(CONTEXT_METNI)
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

// ── 5 Sep 2026: the panel must not go blank while a turn streams ────────────
describe('canlı okuma yapılamadığında', () => {
  it('kullanım son okumayı YAŞIYLA gösteriyor, boş kutu değil', async () => {
    // The numbers `/usage` carries are account-level (quota), not turn-level,
    // so the previous reading is still true while a turn runs. Its age is what
    // keeps it from being read as a fresh measurement.
    cevapla({
      usage: { status: 'ok', text: 'Current session: 22% used', stale: true, age_s: 180, reason: 'busy' },
      context: { status: 'no_data' },
    })
    ciz()
    await waitFor(() => expect(screen.getByTestId('report-stale-usage')).toBeTruthy())
    const metin = screen.getByTestId('session-report-panel').textContent || ''
    expect(metin).toContain('22')
    expect(metin).toContain('3 dk')
  })

  it('taze okumada yaş notu YOK', async () => {
    cevapla({ usage: { status: 'ok', text: 'Current session: 22% used' }, context: { status: 'no_data' } })
    ciz()
    await waitFor(() => expect(screen.getByTestId('session-report-panel').textContent).toContain('22'))
    expect(screen.queryByTestId('report-stale-usage')).toBeNull()
  })

  it('bağlam, kayıtlı yazışmadan türetilen tahmini çiziyor', async () => {
    // The bug this fixes: the context section showed data in NO state at all.
    cevapla({
      usage: { status: 'no_session' },
      context: {
        status: 'estimate',
        reason: 'busy',
        context_usage: {
          percent: 12, should_compact: false, message_count: 8,
          total_chars: 24_500, max_chars: 200_000, estimated: true,
        },
      },
    })
    ciz()
    await waitFor(() => expect(screen.getByTestId('report-context-estimate')).toBeTruthy())
    const metin = screen.getByTestId('report-context-estimate').textContent || ''
    expect(metin).toContain('~%12')
    expect(metin).toContain('8')
    // The estimate must SAY it is an estimate; a bare percentage reads as a
    // measurement, and this one does not see tool output or the system prompt.
    expect(metin).toMatch(/tahmin/i)
  })

  it('tahmin, gerçek rapor kartıyla KARIŞTIRILMIYOR', async () => {
    cevapla({
      usage: { status: 'no_session' },
      context: {
        status: 'estimate',
        context_usage: { percent: 12, should_compact: false, message_count: 8, total_chars: 100, estimated: true },
      },
    })
    ciz()
    await waitFor(() => expect(screen.getByTestId('report-context-estimate')).toBeTruthy())
    // Signature of the `/context` card: "X / Y token". An estimate has NO such number.
    expect(screen.queryByText(/\/ .* token$/)).toBeNull()
    expect(screen.queryByTestId('report-empty-estimate')).toBeNull()
  })

  it('gerçekten hiç veri yoksa bunu açıkça söylüyor', async () => {
    cevapla({ usage: { status: 'no_session' }, context: { status: 'no_data' } })
    ciz()
    await waitFor(() => expect(screen.getByTestId('report-empty-no_data')).toBeTruthy())
  })
})
