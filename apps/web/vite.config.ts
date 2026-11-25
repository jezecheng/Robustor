/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_TARGET = `http://127.0.0.1:${process.env.RB_PORT ?? '8888'}`

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
      '/media': { target: API_TARGET, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
