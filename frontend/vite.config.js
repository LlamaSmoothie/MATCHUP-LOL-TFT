import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const frontendRoot = fileURLToPath(new URL('.', import.meta.url));
const assetsRoot = fileURLToPath(new URL('../assets', import.meta.url));
const dependenciesRoot = fileURLToPath(new URL('../node_modules', import.meta.url));

export default defineConfig({
  root: frontendRoot,
  // Serve/copy the existing images directly, without importing thousands of modules.
  publicDir: assetsRoot,
  cacheDir: fileURLToPath(new URL('../node_modules/.vite', import.meta.url)),
  plugins: [react()],
  build: { assetsInlineLimit: 0 },
  server: {
    fs: { allow: [frontendRoot, assetsRoot, dependenciesRoot] },
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  preview: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
});
