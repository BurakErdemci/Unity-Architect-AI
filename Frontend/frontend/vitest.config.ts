import path from 'node:path'

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // ⚠️ ADLANDIRILMIŞ PLATFORM DİKİŞİ (ölçüldü 2 Ağu 2026). CI bağımlılıkları
  // `npm ci --ignore-scripts` ile kuruyor — bilinçli bir karar, çünkü
  // electron'un postinstall'ı 100MB+ ikili indiriyor ve testlerin o ikiliye
  // ihtiyacı yok. Ama script koşmayınca `electron/index.js` "failed to install
  // correctly" diye FIRLATIYOR ve ana süreç yardımcılarını import eden HER test
  // paketi toplanırken çöküyor. Yerelde ikili kurulu olduğu için hepsi yeşildi:
  // bu deponun kayıtlı "CI kırmızı, yerelde yeşil" sınıfı, üçüncü kez.
  //
  // Alias yalnız ÇALIŞMA ZAMANI çözümünü değiştiriyor; `tsc` hâlâ gerçek
  // electron tiplerini okuduğu için tip güvenliği duruyor.
  resolve: {
    alias: {
      // `@/*` → `renderer/*`, mirroring tsconfig `paths`. Next resolves this at
      // build time; vitest did not, so any test that imported a component using
      // the alias failed to COLLECT — not a red assertion but a missing file,
      // which is the quieter failure of the two. Measured when the first test
      // for `renderer/components/ui/animated-ai-chat.tsx` was written.
      '@': path.resolve(__dirname, 'renderer'),
      electron: path.resolve(__dirname, '__tests__/stubs/electron.ts'),
      'electron-store': path.resolve(__dirname, '__tests__/stubs/electron-store.ts'),
    },
  },
  test: {
    environment: 'jsdom',
    // Node'un kullanılamaz `localStorage` global'ini değiştiriyor; gerekçe ve
    // ölçüm o dosyanın başında. Kurulum olmadan bu ağaçta 42 test kırmızı.
    setupFiles: ['./vitest.setup.ts'],
    // `.tsx` DAHİL olmak zorunda: desen yalnız `.test.ts` iken bir bileşen
    // testi yazmak imkânsızdı — dosya diske yazılıyor, vitest onu hiç
    // toplamıyor ve koşu YEŞİL raporlanıyordu. Sessiz test kaybı, yani
    // sahte yeşilin en pahalı biçimi. (Ölçüldü 2026-07-30: üç yeni `.test.tsx`
    // dosyası eklendi, koşu yine "11 dosya" dedi.)
    include: ['__tests__/**/*.test.{ts,tsx}'],
    globals: true,
    coverage: {
      provider: 'v8',
      include: ['main/helpers/**/*.ts', 'renderer/components/ui/Toast.tsx'],
    },
  },
})
