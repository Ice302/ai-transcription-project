import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Backend address for the dev proxy. Override with BACKEND_URL if port 8000 is taken.
const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Same-origin API calls in development: no CORS, no hard-coded backend URL.
    proxy: {
      '/api': { target: backend, changeOrigin: true, ws: true },
    },
  },
})
