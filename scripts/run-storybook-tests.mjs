import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, join, normalize, resolve, sep } from 'node:path';

const ROOT = resolve('storybook-static');
const PORT = Number(process.env.STORYBOOK_TEST_PORT ?? 6006);
const HOST = '127.0.0.1';

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.map': 'application/json; charset=utf-8',
};

if (!existsSync(ROOT)) {
  console.error('storybook-static is missing; run "npm run build-storybook" first.');
  process.exit(1);
}

function resolveRequestPath(url) {
  const pathname = decodeURIComponent(new URL(url, `http://${HOST}`).pathname);
  const candidate = normalize(join(ROOT, pathname));
  if (candidate !== ROOT && !candidate.startsWith(ROOT + sep)) {
    return null;
  }
  if (existsSync(candidate) && statSync(candidate).isDirectory()) {
    return join(candidate, 'index.html');
  }
  return candidate;
}

const server = createServer((request, response) => {
  const filePath = resolveRequestPath(request.url ?? '/');
  if (!filePath || !existsSync(filePath)) {
    response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    response.end('Not found');
    return;
  }
  response.writeHead(200, {
    'content-type': CONTENT_TYPES[extname(filePath)] ?? 'application/octet-stream',
    'cache-control': 'no-store',
  });
  createReadStream(filePath).pipe(response);
});

server.listen(PORT, HOST, () => {
  const runner = spawn(
    process.execPath,
    [
      './node_modules/.bin/test-storybook',
      '--url',
      `http://${HOST}:${PORT}`,
      '--index-json',
      '--ci',
      '--failOnConsole',
      ...process.argv.slice(2),
    ],
    { stdio: 'inherit' },
  );
  runner.on('exit', (code, signal) => {
    server.close(() => process.exit(signal ? 1 : code ?? 1));
  });
});
