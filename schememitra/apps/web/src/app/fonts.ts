import {
  Noto_Naskh_Arabic,
  Noto_Sans,
  Noto_Sans_Bengali,
  Noto_Sans_Devanagari,
  Noto_Sans_Gujarati,
  Noto_Sans_Gurmukhi,
  Noto_Sans_Kannada,
  Noto_Sans_Malayalam,
  Noto_Sans_Oriya,
  Noto_Sans_Tamil,
  Noto_Sans_Telugu,
} from 'next/font/google';
import type { LocaleCode } from '@sm/i18n';

// next/font self-hosts every face at build time. Only the Latin face is preloaded; a script
// face downloads the first time text in that script is rendered, so a Gujarati user never
// fetches Tamil glyphs (spec §7: load only the active script).
const latin = Noto_Sans({ subsets: ['latin'], display: 'swap', weight: ['400', '600', '700'], variable: '--sm-font-latin' });
const deva = Noto_Sans_Devanagari({ subsets: ['devanagari'], display: 'swap', preload: false, weight: ['400', '600', '700'] });
const beng = Noto_Sans_Bengali({ subsets: ['bengali'], display: 'swap', preload: false, weight: ['400', '600', '700'] });
const gujr = Noto_Sans_Gujarati({ subsets: ['gujarati'], display: 'swap', preload: false, weight: ['400', '600', '700'] });
const guru = Noto_Sans_Gurmukhi({ subsets: ['gurmukhi'], display: 'swap', preload: false, weight: ['400', '600', '700'] });
const knda = Noto_Sans_Kannada({ subsets: ['kannada'], display: 'swap', preload: false, weight: ['400', '600', '700'] });
const mlym = Noto_Sans_Malayalam({ subsets: ['malayalam'], display: 'swap', preload: false, weight: ['400', '600', '700'] });
const orya = Noto_Sans_Oriya({ subsets: ['oriya'], display: 'swap', preload: false, weight: ['400', '600', '700'] });
const taml = Noto_Sans_Tamil({ subsets: ['tamil'], display: 'swap', preload: false, weight: ['400', '600', '700'] });
const telu = Noto_Sans_Telugu({ subsets: ['telugu'], display: 'swap', preload: false, weight: ['400', '600', '700'] });
const arab = Noto_Naskh_Arabic({ subsets: ['arabic'], display: 'swap', preload: false, weight: ['400', '600', '700'] });

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
