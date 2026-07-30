import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
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
