// CI gate for translations (ADR-012):
//  1. every citizen-facing key in en.json exists in all 13 locales as a non-empty string,
//  2. placeholders like {amount} match the English source exactly,
//  3. officer-facing namespaces are required only in en + hi,
//  4. no locale carries keys the source no longer has (stale keys).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const languages = JSON.parse(readFileSync(join(root, 'languages.json'), 'utf8'));
const OFFICER_NAMESPACES = new Set(['officer']);
const OFFICER_LOCALES = new Set(['en', 'hi']);

const flatten = (obj, prefix = '') =>
  Object.entries(obj).flatMap(([k, v]) =>
    k === '_meta'
      ? []
      : v && typeof v === 'object'
        ? flatten(v, `${prefix}${k}.`)
        : [[`${prefix}${k}`, v]],
  );
const placeholders = (s) =>
  [...String(s).matchAll(/\{(\w+)\}/g)]
    .map((m) => m[1])
    .sort()
    .join(',');
const load = (code) =>
  Object.fromEntries(flatten(JSON.parse(readFileSync(join(root, 'locales', `${code}.json`), 'utf8'))));

const source = load('en');
let problems = 0;
const report = (msg) => {
  problems++;
  console.error(msg);
};

for (const { code } of languages) {
  const target = load(code);
  for (const [key, text] of Object.entries(source)) {
    const ns = key.split('.')[0];
    if (OFFICER_NAMESPACES.has(ns) && !OFFICER_LOCALES.has(code)) continue;
    if (typeof target[key] !== 'string' || target[key].trim() === '') {
      report(`[${code}] missing ${key}`);
    } else if (placeholders(target[key]) !== placeholders(text)) {
      report(`[${code}] placeholder mismatch in ${key}: "${target[key]}"`);
    }
  }
  for (const key of Object.keys(target)) {
    if (!(key in source)) report(`[${code}] stale key ${key}`);
  }
}

if (problems) {
  console.error(`\n${problems} i18n problems`);
  process.exit(1);
}
console.log(`i18n OK: ${Object.keys(source).length} source keys checked across ${languages.length} locales.`);
