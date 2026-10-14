import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { existsSync, unlinkSync } from 'node:fs';
import { resolve } from 'node:path';

// Keep the build-time source catalog for compatibility, never distribute its full text.
const privateCatalog = () => ({
  name: 'private-policy-catalog',
  configureServer(server: { middlewares: { use: (handler: (req: { url?: string }, res: { statusCode: number; end: () => void }, next: () => void) => void) => void } }) {
    server.middlewares.use((req, res, next) => {
      let path: string;
      try { path = decodeURIComponent((req.url || '').split('?')[0]); }
      catch { res.statusCode = 400; res.end(); return; }
      if (/production-quality-rules\.json$/.test(path)) { res.statusCode = 404; res.end(); } else next();
    });
  },
  closeBundle() {
    const path = resolve('dist/production-quality-rules.json');
    if (existsSync(path)) unlinkSync(path); // Generated build artifact only, never source.
  },
});

export default defineConfig({
  plugins: [react(), privateCatalog()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  preview: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
