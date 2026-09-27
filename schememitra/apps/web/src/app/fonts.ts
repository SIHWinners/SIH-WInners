import type { LocaleCode } from '@sm/i18n';
import localFont from 'next/font/local';

/**
 * Self-hosted Noto faces (ADR-021). The same TTFs that go into the loan-file PDF are subsetted
 * to woff2 by `scripts/build-webfonts.py`, so type is identical on screen and on paper, the
 * build needs no internet, and no third party sees who is reading the page.
 *
 * Only the Latin face is preloaded. A script face is fetched the first time text in that script
 * renders, so a Gujarati reader downloads ~150 KB of type rather than every Indian script
 * (spec §7, claim C14). next/font requires literal calls at module scope, hence the repetition.
 */
const latin = localFont({
  src: [
    { path: './fonts/latin-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/latin-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: true,
  fallback: ['system-ui', 'sans-serif'],
  variable: '--sm-font-latin',
});
const deva = localFont({
  src: [
    { path: './fonts/devanagari-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/devanagari-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});
const beng = localFont({
  src: [
    { path: './fonts/bengali-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/bengali-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});
const gujr = localFont({
  src: [
    { path: './fonts/gujarati-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/gujarati-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});
const guru = localFont({
  src: [
    { path: './fonts/gurmukhi-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/gurmukhi-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});
const knda = localFont({
  src: [
    { path: './fonts/kannada-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/kannada-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});
const mlym = localFont({
  src: [
    { path: './fonts/malayalam-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/malayalam-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});
const orya = localFont({
  src: [
    { path: './fonts/oriya-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/oriya-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});
const taml = localFont({
  src: [
    { path: './fonts/tamil-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/tamil-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});
const telu = localFont({
  src: [
    { path: './fonts/telugu-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/telugu-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});
const arab = localFont({
  src: [
    { path: './fonts/arabic-400.woff2', weight: '400', style: 'normal' },
    { path: './fonts/arabic-700.woff2', weight: '700', style: 'normal' },
  ],
  display: 'swap',
  preload: false,
  fallback: ['system-ui', 'sans-serif'],
});

const byLocale: Record<LocaleCode, { style: { fontFamily: string } } | null> = {
  en: null,
  hi: deva,
  mr: deva,
  bn: beng,
  as: beng,
  gu: gujr,
  pa: guru,
  kn: knda,
  ml: mlym,
  or: orya,
  ta: taml,
  te: telu,
  ur: arab,
};

/** CSS font stack for the active locale: its script face first, Latin as fallback for digits/brand. */
export function fontStackFor(locale: LocaleCode): string {
  const script = byLocale[locale];
  return [script?.style.fontFamily, latin.style.fontFamily].filter(Boolean).join(', ');
}

export const latinFontClass = latin.variable;
