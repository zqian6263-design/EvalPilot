import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frozen contract (docs/INTERFACES.md) puts everything under /api.
// The dev proxy forwards that prefix to the FastAPI backend so the browser
// sees a same-origin API and no CORS configuration is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind IPv4 explicitly. Vite's default resolves `localhost`, which on
    // Windows prefers the IPv6 loopback `::1`, so a tool that probes
    // 127.0.0.1 - the start script's health gate, an e2e check, curl - finds
    // nothing listening even though the server printed "ready". The proxy
    // target below is IPv4 too, so both sides of the connection agree.
    host: '127.0.0.1',
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
