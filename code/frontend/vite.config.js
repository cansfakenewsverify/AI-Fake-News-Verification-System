import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 開發時將 /api 請求代理到後端，避免 CORS 問題
      // 部署到雲端時由 nginx 負責代理，不需要改程式碼
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
