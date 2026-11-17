import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

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
    // Three pages, one build (ui/live-apps): the walkthrough at /, the customer app at /customer/
    // and the Westpac dashboard at /westpac/ (web/dist/<app>/index.html, served by app.py).
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        customer: fileURLToPath(new URL('./customer/index.html', import.meta.url)),
        westpac: fileURLToPath(new URL('./westpac/index.html', import.meta.url)),
      },
    },
  },
});
