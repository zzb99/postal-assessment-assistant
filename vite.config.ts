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
  // 职工网页与微信小程序共用的填报逻辑（纯 TypeScript），源码放在小程序目录内，小程序可直接编译。
  resolve: { alias: { '@shared': resolve('miniprogram/src/shared') } },
  server: { proxy: { '/api': process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000' },
    watch: { ignored: ['**/output/**', '**/.tmp/**', '**/.pytest_cache/**', '**/.venv/**'] } },
  preview: { proxy: { '/api': process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000' } },
});
