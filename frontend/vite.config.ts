import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frozen contract (docs/INTERFACES.md) puts everything under /api.
// The dev proxy forwards that prefix to the FastAPI backend so the browser
// sees a same-origin API and no CORS configuration is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
