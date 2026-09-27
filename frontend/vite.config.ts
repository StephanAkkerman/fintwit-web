import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  // API_KEY lives in the repo-root .env next to the backend's settings. The
  // proxy attaches it server-side, like nginx does in Docker, so the key never
  // ends up in the browser bundle.
  const { API_KEY: apiKey = '' } = loadEnv(mode, '..', '')
  const backend = {
    target: 'http://127.0.0.1:7999',
    changeOrigin: true,
    headers: apiKey ? { 'X-API-Key': apiKey } : undefined,
  }

  return {
    plugins: [react()],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/setupTests.ts',
    },
    server: {
      port: 5173,
      host: true,
      proxy: {
        '/api': backend,
        '/healthz': backend,
      },
    },
  }
})
