// Fails CI when any declared token pair drops below WCAG 2.2 AA, in light or dark.
// Also verifies tokens.css and tokens.ts agree, so the web and mobile palettes cannot drift.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const tsSource = readFileSync(join(here, '../src/tokens.ts'), 'utf8');
const cssSource = readFileSync(join(here, '../src/tokens.css'), 'utf8');

function block(name) {
  const start = tsSource.indexOf(`${name}: {`);
  const end = tsSource.indexOf('}', start);
  return Object.fromEntries(
    [...tsSource.slice(start, end).matchAll(/(\w+): '(#[0-9A-Fa-f]{6})'/g)].map((m) => [m[1], m[2]]),
  );
}

const palettes = { light: block('light'), dark: block('dark') };
const pairs = [...tsSource.matchAll(/\{ fg: '(\w+)', bg: '(\w+)', kind: '(text|ui)' \}/g)].map((m) => ({
  fg: m[1],
  bg: m[2],
  kind: m[3],
}));

const channel = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const luminance = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => channel(parseInt(hex.slice(i, i + 2), 16) / 255));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

const kebab = (s) => s.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
let failures = 0;

for (const [scheme, palette] of Object.entries(palettes)) {
  for (const { fg, bg, kind } of pairs) {
    const r = ratio(palette[fg], palette[bg]);
    const min = kind === 'text' ? 4.5 : 3;
    const ok = r >= min;
    if (!ok) failures++;
    console.log(`${ok ? 'ok  ' : 'FAIL'} ${scheme.padEnd(5)} ${fg} on ${bg} = ${r.toFixed(2)} (min ${min})`);
  }
  // tokens.css must define the same values
  for (const [token, value] of Object.entries(palette)) {
    const selector = scheme === 'light' ? ':root' : '[data-theme="dark"]';
    const section = cssSource.slice(cssSource.indexOf(selector));
    const match = section.match(new RegExp(`--sm-${kebab(token)}:\\s*(#[0-9A-Fa-f]{6})`));
    if (!match || match[1].toUpperCase() !== value.toUpperCase()) {
      failures++;
      console.log(`FAIL ${scheme} tokens.css --sm-${kebab(token)} expected ${value}, got ${match?.[1]}`);
    }
  }
}

if (failures) {
  console.error(`\n${failures} contrast/token problems`);
  process.exit(1);
}
console.log('\nAll colour pairs meet WCAG 2.2 AA and CSS matches TS tokens.');
