import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // Proxy API requests to backend (backend doesn't use /api prefix)
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      '/topology': { target: 'http://localhost:8000', changeOrigin: true },
      '/devices': { target: 'http://localhost:8000', changeOrigin: true },
      '/checks': { target: 'http://localhost:8000', changeOrigin: true },
      '/alerts': { target: 'http://localhost:8000', changeOrigin: true },
      '/stats': { target: 'http://localhost:8000', changeOrigin: true },
      '/discover': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
