import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/health': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
