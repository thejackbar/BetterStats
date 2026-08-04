import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_BASE: the path prefix a silo build lives under (e.g. '/afl/' for the
// betterat.football umbrella — see docs/afl-betterstats-plan.md). Unset/empty
// = root, the cricket default.
const BASE = process.env.VITE_BASE || '/'
const PROXY_TARGET = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'
// Under a base path the app calls '<base>api' (see lib/api.js), so dev needs a
// matching proxy entry, stripping the prefix the same way nginx does in prod.
const basedApiProxy = BASE !== '/' ? {
  [`${BASE.replace(/\/$/, '')}/api`]: {
    target: PROXY_TARGET,
    changeOrigin: true,
    rewrite: (path) => path.replace(new RegExp(`^${BASE.replace(/\/$/, '')}/api`), ''),
  },
} : {}

export default defineConfig({
  base: BASE,
  plugins: [react()],
  optimizeDeps: {
    exclude: ['@imgly/background-removal'],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['react', 'react-dom', 'react-router-dom'],
          'charts': ['recharts'],
          'canvas': ['modern-screenshot'],
        },
      },
    },
  },
  server: {
    proxy: {
      ...basedApiProxy,
      '/api': {
        // Override with VITE_PROXY_TARGET to point local dev at a different
        // backend (e.g. the AFL silo, or production for visual checks).
        target: PROXY_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/images': {
        target: PROXY_TARGET,
        changeOrigin: true,
      },
    },
  },
})
