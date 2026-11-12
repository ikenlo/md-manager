import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// MDS_API_TARGET — інший бекенд (e2e-тести на власному порту). Без @types/node — через globalThis.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const apiTarget = env.MDS_API_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // /api і WebSocket /api/ws → бекенд
    proxy: { '/api': { target: apiTarget, ws: true } },
  },
});
