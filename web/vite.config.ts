import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'

// https://vite.dev/config/
// Dev proxy mirrors prod nginx routing. Only /api/* proxies to the
// backend; bare paths are served by Vite's SPA fallback.
//
// Route strategy: some FastAPI routes have /api prefix (auth, config,
// health/db, health/ready, checks/defaults), others don't (devices,
// topology, checks, health, etc). This list maps FE paths to whether
// the /api prefix is preserved or stripped on forward.
const PRESERVE_API_PREFIX = new Set([
  '/api/auth/login',
  '/api/auth/signup',
  '/api/auth/me',
  '/api/auth/logout',
  '/api/auth/change-password',
  '/api/config',
  '/api/config/profiles',
  '/api/config/profile',
  '/api/config/traps',
  '/api/health/db',
  '/api/health/ready',
  '/api/checks/defaults',
]);

// Prefix-based passthrough for groups where every sub-route has /api.
const API_PREFIX_GROUPS = ['/api/auth/', '/api/config/'];

export default defineConfig({
  plugins: [react()],
  server: {
    https: {
      key: fs.readFileSync('/home/cqrtp/.vite-plugin-mkcert/dev.pem'),
      cert: fs.readFileSync('/home/cqrtp/.vite-plugin-mkcert/cert.pem'),
    },
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => {
          if (PRESERVE_API_PREFIX.has(path)) return path;
          if (API_PREFIX_GROUPS.some((p) => path.startsWith(p))) return path;
          return path.replace(/^\/api/, '');
        },
        // SSE streams must not be buffered by the proxy
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes, req) => {
            if (req.url?.includes('/stream')) {
              // Disable proxy buffering for SSE
              proxyRes.headers['cache-control'] = 'no-cache';
              proxyRes.headers['x-accel-buffering'] = 'no';
            }
          });
        },
      },
    },
  },
})
