// Deep-merges a patch file of the shape { "<locale>": { ...nested keys } } into the locale
// catalogues, preserving key order of existing entries. Usage:
//   node packages/i18n/scripts/merge.mjs path/to/patch.json
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const patchPath = process.argv[2];
if (!patchPath) {
  console.error('usage: merge.mjs <patch.json>');
  process.exit(2);
}
const patch = JSON.parse(readFileSync(patchPath, 'utf8'));

function merge(target, source) {
  for (const [key, value] of Object.entries(source)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      target[key] = merge(target[key] && typeof target[key] === 'object' ? target[key] : {}, value);
    } else {
      target[key] = value;
    }
  }
  return target;
}

for (const [locale, entries] of Object.entries(patch)) {
  const file = join(root, 'locales', `${locale}.json`);
  const current = JSON.parse(readFileSync(file, 'utf8'));
  writeFileSync(file, `${JSON.stringify(merge(current, entries), null, 2)}\n`);
  console.log(`merged into ${locale}.json`);
}
