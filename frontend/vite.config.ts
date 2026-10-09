import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  // strictPort: fail instead of silently moving to 5174, which the API's CORS list does not allow.
  server: { port: 5173, strictPort: true },
  test: {
    environment: 'jsdom', // a fake browser DOM inside Node, so components can render in tests
    setupFiles: ['src/test/setup.ts'],
  },
})
