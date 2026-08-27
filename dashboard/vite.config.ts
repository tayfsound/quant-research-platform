import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  server: {
    // Tailscale/aynı ağdaki diğer cihazlardan (telefon) erişim için —
    // sadece localhost yerine tüm arayüzlerde dinliyor. Tailscale özel
    // bir ağ olduğu için genel internete açık değil, güvenlik riski yok.
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  plugins: [react(), tailwindcss()],
})
