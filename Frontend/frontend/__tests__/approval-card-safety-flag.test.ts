/**
 * Güvenlik kontrolleri kapalıysa onay kartı bunu BAĞIRMALI.
 *
 * Canlı testte ölçüldü (31 Tem 2026): engellenen bir desenle karşılaşan model
 * kullanıcıya `safety_checks: false` ile devam etmeyi önerdi. Şema tarafı ayrıca
 * düzeltildi (bkz. Server/tests/test_execute_code_schema.py), ama bayrak hâlâ
 * meşru olarak gönderilebiliyor — o zaman kararın en önemli parçası kartta
 * GÖRÜNÜR olmalı.
 *
 * Eskiden `safety_checks: false` yalnız parametre döngüsünde, uzun bir kod
 * gövdesinin altında sıradan bir satır olarak yazılıyordu. Kullanıcı kodu okuyup
 * bayrağı kaçırır; kart teknik olarak "dürüst" ama pratikte sessizdir.
 *
 * ⚠️ Koşul bilerek "true değilse", "=== false" DEĞİL. Karar veren kod
 * fail-CLOSED (`is True`), gösteren kod fail-LOUD olmalı: bozuk bir yük
 * (`"false"`, `0`) uyarıyı düşürmemeli — güvenilmez yük, uyarının en çok
 * gerektiği yerdir.
 */
import { describe, it, expect } from 'vitest'
import { unityOzeti } from '../renderer/hooks/home/useMCPApproval'

const UYARI = 'GÜVENLİK KONTROLLERİ KAPALI'

describe('unityOzeti · güvenlik bayrağı', () => {
  it('safety_checks false ise kartta uyarı VAR', () => {
    const ozet = unityOzeti('execute_code', {
      action: 'execute',
      safety_checks: false,
      code: 'System.IO.File.Delete("x");',
    })
    expect(ozet).toContain(UYARI)
  })

  it('uyarı KOD GÖVDESİNDEN ÖNCE gelir', () => {
    // Sıra kozmetik değil: uzun bir kod bloğunun altına düşen uyarı,
    // düzeltmeden önceki sessiz satırın aynısı olurdu.
    const uzunKod = 'var x = 1;\n'.repeat(300)
    const ozet = unityOzeti('execute_code', { action: 'execute', code: uzunKod, safety_checks: false })
    expect(ozet.indexOf(UYARI)).toBeLessThan(ozet.indexOf('code:'))
  })

  it('BOZUK yük de uyarı üretir — fail-LOUD', () => {
    for (const bozuk of ['false', 0, null, 'hayır']) {
      const ozet = unityOzeti('execute_code', { action: 'execute', safety_checks: bozuk as any })
      expect(ozet, `değer: ${JSON.stringify(bozuk)}`).toContain(UYARI)
    }
  })

  it('TERS YÖN: safety_checks true ise uyarı YOK', () => {
    const ozet = unityOzeti('execute_code', { action: 'execute', safety_checks: true, code: 'return 1;' })
    expect(ozet).not.toContain(UYARI)
  })

  it('TERS YÖN: bayrak hiç gönderilmemişse uyarı YOK', () => {
    // Varsayılan zaten açık; her karta uyarı basmak onu görünmez yapardı —
    // refleks-onayı besleyen şeyin ta kendisi.
    const ozet = unityOzeti('manage_gameobject', { action: 'create', name: 'KapiTesti' })
    expect(ozet).not.toContain(UYARI)
  })

  it('hedef proje satırı KORUNUYOR', () => {
    // Uyarı en üste eklenirken `unity_instance`ın üstteki yeri bozulmamalı;
    // ikisi de kararın parçası ve biri diğerini itemez.
    const ozet = unityOzeti('execute_code', {
      unity_instance: 'Korebe@abc123',
      action: 'execute',
      safety_checks: false,
    })
    expect(ozet).toContain('unity_instance: Korebe@abc123')
    expect(ozet).toContain(UYARI)
  })
})
