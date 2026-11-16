import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// `npm run dev` serves the UI on 127.0.0.1:5173 and forwards /api to `python app.py` (127.0.0.1:8600).
// `npm run build` writes web/dist, which app.py serves at / (one command, one port).
const API = process.env.GUARDIAN_API ?? 'http://127.0.0.1:8600';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': API },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 2000,
  },
});
