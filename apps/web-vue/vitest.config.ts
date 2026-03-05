import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: [],
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{ts,vue}'],
      thresholds: {
        statements: 20,
        branches: 60,
        functions: 40,
        lines: 20,
      },
      exclude: [
        'src/main.ts',
        'src/**/*.d.ts',
        'src/**/*.test.ts',
        'src/**/__tests__/**',
      ],
    },
  },
})
