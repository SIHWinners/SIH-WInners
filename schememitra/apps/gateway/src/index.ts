import { loadConfig } from './config.js';
import { buildServer } from './server.js';

const cfg = loadConfig();
const app = await buildServer(cfg);

try {
  await app.listen({ port: cfg.port, host: cfg.host });
} catch (err) {
  app.log.error(err);
  process.exit(1);
}

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.on(signal, () => {
    void app.close().then(() => process.exit(0));
  });
}
