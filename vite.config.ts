import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { viteSingleFile } from 'vite-plugin-singlefile'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  server: {
    watch: {
      ignored: ['**/data/**', '**/public/data/**'],
    },
  },
  plugins: [
    tailwindcss(),
    react(),
    viteSingleFile(),
  ],
})
