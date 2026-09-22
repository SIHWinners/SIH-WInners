#!/usr/bin/env node
// Cross-platform task runner (ADR-006). `make <target>` on Linux/macOS and
// `pnpm <target>` / `node scripts/make.mjs <target>` on Windows do the same thing.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CORE = join(ROOT, 'services', 'core');
const WEB = join(ROOT, 'apps', 'web');
const GATEWAY = join(ROOT, 'apps', 'gateway');
const isWin = process.platform === 'win32';

function loadEnv() {
  const env = { ...process.env, PYTHONIOENCODING: 'utf-8', NEXT_TELEMETRY_DISABLED: '1' };
  const file = join(ROOT, '.env');
  if (existsSync(file)) {
    for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
      const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (!match || match[1] in process.env) continue;
      const raw = match[2];
      // Quoted values are taken literally; unquoted values drop a trailing " # comment".
      env[match[1]] = /^["']/.test(raw) ? raw.replace(/^["']|["']$/g, '') : raw.replace(/(^|\s+)#.*$/, '').trim();
    }
  }
  return env;
}

const ENV = loadEnv();
const COLORS = { core: 36, gateway: 35, web: 33, worker: 32 };

function run(cmd, cwd, extraEnv = {}) {
  console.log(`\x1b[2m$ ${cmd}\x1b[0m`);
  const res = spawnSync(cmd, { cwd, shell: true, stdio: 'inherit', env: { ...ENV, ...extraEnv } });
  if (res.status !== 0) {
    console.error(`\n✗ failed: ${cmd}`);
    process.exit(res.status ?? 1);
  }
}

function serve(name, cmd, cwd, extraEnv = {}) {
  const child = spawn(cmd, { cwd, shell: true, env: { ...ENV, ...extraEnv } });
  const tag = `\x1b[${COLORS[name] ?? 37}m${name.padEnd(8)}\x1b[0m│ `;
  const pipe = (stream) =>
    stream.on('data', (chunk) => {
      for (const line of chunk.toString().split(/\r?\n/)) if (line.trim()) process.stdout.write(tag + line + '\n');
    });
  pipe(child.stdout);
  pipe(child.stderr);
  child.on('exit', (code) => console.log(`${tag}exited (${code})`));
  return child;
}

function keepAlive(children) {
  const stop = () => {
    for (const child of children) {
      if (isWin) spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
      else child.kill('SIGTERM');
    }
    process.exit(0);
  };
  process.on('SIGINT', stop);
  process.on('SIGTERM', stop);
}

const uv = (args) => `uv run ${args}`;
const migrate = () => run(uv('alembic upgrade head'), CORE);
const seed = () => run(uv('python -m app.seed'), CORE);

function banner() {
  console.log(`
  SchemeMitra is starting
  ─────────────────────────────────────────────
  Citizen PWA      http://localhost:3000
  Partner portal   http://localhost:3000/partner
  Admin console    http://localhost:3000/admin
  Policy insights  http://localhost:3000/insights
  Gateway          http://localhost:8080/healthz
  Core API docs    http://localhost:8000/docs
  Demo sign-in     http://localhost:3000/login (OTP shown on screen in demo mode)
`);
}

const targets = {
  setup() {
    run('pnpm install', ROOT);
    run('uv sync --extra dev', CORE);
  },
  migrate,
  seed() {
    migrate();
    seed();
  },
  reset() {
    rmSync(join(CORE, 'var', 'schememitra.db'), { force: true });
    rmSync(join(CORE, 'var', 'schememitra.db-wal'), { force: true });
    rmSync(join(CORE, 'var', 'schememitra.db-shm'), { force: true });
    rmSync(join(CORE, 'var', 'objects'), { recursive: true, force: true });
    migrate();
    seed();
  },
  contracts() {
    run(uv('python -m app.cli export-openapi ../../packages/contracts/openapi.json'), CORE);
    run('pnpm --filter @sm/contracts generate', ROOT);
  },
  dev() {
    migrate();
    if (!existsSync(join(CORE, 'var', '.seeded'))) seed();
    banner();
    keepAlive([
      serve('core', uv('uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload --reload-dir app --timeout-graceful-shutdown 3'), CORE),
      serve('gateway', 'pnpm dev', GATEWAY),
      serve('web', 'pnpm dev', WEB),
    ]);
  },
  demo() {
    // Production builds, sandbox adapters, zero internet required once dependencies are installed.
    migrate();
    if (!existsSync(join(CORE, 'var', '.seeded'))) seed();
    if (!existsSync(join(WEB, '.next', 'BUILD_ID'))) run('pnpm build', WEB);
    banner();
    const demoEnv = { DEMO_MODE: 'true', NODE_ENV: 'production', INSECURE_COOKIES: '1' };
    keepAlive([
      serve('core', uv('uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1'), CORE, demoEnv),
      serve('gateway', 'pnpm start', GATEWAY, demoEnv),
      serve('web', 'pnpm start', WEB, demoEnv),
    ]);
  },
  test() {
    run(uv('pytest -q'), CORE, { LIGHT_MODE: '1' });
    run('node packages/i18n/scripts/check-keys.mjs', ROOT);
    run('node packages/ui/scripts/check-contrast.mjs', ROOT);
    run('pnpm -r --if-present test', ROOT);
  },
  lint() {
    run(uv('ruff check app tests'), CORE);
    run('pnpm -r --if-present lint', ROOT);
  },
  typecheck() {
    run(uv('mypy app'), CORE);
    run('pnpm -r --if-present typecheck', ROOT);
  },
  e2e() {
    run('pnpm --filter @sm/e2e test', ROOT);
  },
  models() {
    // Heavy, optional. Each step falls back gracefully if it fails (spec §19.3).
    const soft = (cmd, cwd) => {
      console.log(`\x1b[2m$ ${cmd}\x1b[0m`);
      const res = spawnSync(cmd, { cwd, shell: true, stdio: 'inherit', env: ENV });
      if (res.status !== 0) console.warn(`! skipped (fallback stays active): ${cmd}`);
    };
    soft('uv sync --extra dev --extra ocr', CORE);
    soft(uv('python -m app.cli warm-ocr'), CORE);
    soft('uv sync --extra dev --extra ocr --extra asr', CORE);
    soft(uv('python -m app.cli warm-asr'), CORE);
    soft(`ollama pull ${ENV.LLM_MODEL ?? 'llama3.1:8b'}`, ROOT);
    run(uv('python -m ml.train'), CORE);
  },
};

const target = process.argv[2];
if (!target || !(target in targets)) {
  console.log(`usage: node scripts/make.mjs <${Object.keys(targets).join('|')}>`);
  process.exit(target ? 1 : 0);
}
targets[target]();
