import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// Dev proxy mirrors prod nginx routing. Only /api/* proxies to
// the backend; bare paths are served by Vite's SPA fallback.
// The /api prefix is stripped on forward EXCEPT for the auth
// and config routers, which FastAPI mounts under /api/auth and
// /api/config. Keep this list in sync with docker/nginx.conf.
const PASSTHROUGH_API_PREFIXES = ['/api/auth', '/api/config'];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => {
          // Keep /api prefix for auth/config routes (backend
          // mounts them there). Strip for everything else.
          if (PASSTHROUGH_API_PREFIXES.some((p) => path === p || path.startsWith(p + '/'))) {
            return path;
          }
          return path.replace(/^\/api/, '');
        },
      },
    },
  },
})
