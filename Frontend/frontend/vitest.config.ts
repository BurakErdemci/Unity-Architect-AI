import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['__tests__/**/*.test.ts'],
    globals: true,
    coverage: {
      provider: 'v8',
      include: ['main/helpers/**/*.ts', 'renderer/components/ui/Toast.tsx'],
    },
  },
})
