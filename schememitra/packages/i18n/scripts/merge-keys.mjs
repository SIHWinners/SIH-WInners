// Deep-merges a {locale: {namespace: {...}}} JSON file into the locale catalogues.
// Used when a feature adds strings: write them once, merge into all 13 files.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const merge = (target, add) => {
  for (const [key, value] of Object.entries(add)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) merge((target[key] ??= {}), value);
    else target[key] = value;
  }
};
for (const [locale, keys] of Object.entries(source)) {
  const path = join(root, 'locales', `${locale}.json`);
  const data = JSON.parse(readFileSync(path, 'utf8'));
  merge(data, keys);
  writeFileSync(path, JSON.stringify(data, null, 2) + '\n');
}
console.log(`merged ${Object.keys(source).length} locales`);
