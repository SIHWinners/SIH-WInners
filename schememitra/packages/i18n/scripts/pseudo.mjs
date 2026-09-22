// Writes locales/pseudo.json: English stretched ~40% with accented vowels, so overflow and
// truncation bugs for long Indic strings show up while developing in English.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const en = JSON.parse(readFileSync(join(root, 'locales/en.json'), 'utf8'));
const accents = { a: 'á', e: 'ë', i: 'ï', o: 'ô', u: 'ü', A: 'Å', E: 'É', O: 'Ö' };

function stretch(text) {
  const body = text
    .split(/(\{\w+\})/)
    .map((part) => (part.startsWith('{') ? part : part.replace(/[aeiouAEO]/g, (c) => accents[c])))
    .join('');
  return `⟦${body}${'·'.repeat(Math.ceil(text.length * 0.4))}⟧`;
}

function walk(node) {
  return Object.fromEntries(
    Object.entries(node).map(([k, v]) => {
      if (k === '_meta') return [k, { language: 'Pseudo', review_status: 'generated' }];
      return [k, typeof v === 'string' ? stretch(v) : walk(v)];
    }),
  );
}

writeFileSync(join(root, 'locales/pseudo.json'), JSON.stringify(walk(en), null, 2));
console.log('locales/pseudo.json written');
