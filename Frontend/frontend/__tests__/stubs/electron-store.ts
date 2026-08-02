/**
 * `electron-store`un TEST karşılığı.
 *
 * Gerekçesi `stubs/electron.ts`'in başında: bu paket modül düzeyinde
 * `require('electron')` yapıyor, dolayısıyla electron stub'ı tek başına
 * yetmiyordu — `create-window.ts`'i import eden testler bu zincirden çöküyordu.
 *
 * Bellek içi bir sözlük yeterli: `Store` yalnız `createWindow` içinde pencere
 * boyutunu saklamak için kullanılıyor ve testler o fonksiyonu çağırmıyor.
 */
export default class Store<T = unknown> {
  private kayit = new Map<string, unknown>()

  constructor(_secenekler?: unknown) {}

  get(anahtar: string, varsayilan?: T): T {
    return (this.kayit.has(anahtar) ? this.kayit.get(anahtar) : varsayilan) as T
  }

  set(anahtar: string, deger: T): void {
    this.kayit.set(anahtar, deger)
  }

  delete(anahtar: string): void {
    this.kayit.delete(anahtar)
  }
}
