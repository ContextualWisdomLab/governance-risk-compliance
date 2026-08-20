import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests',
  testMatch: 'buyer-workspace.spec.mjs',
  timeout: 10_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    serviceWorkers: 'block',
  },
  webServer: {
    command: 'python3 -m http.server 4173 --bind 127.0.0.1 --directory .',
    url: 'http://127.0.0.1:4173/apps/grc-workspace/index.html',
    reuseExistingServer: false,
  },
});
