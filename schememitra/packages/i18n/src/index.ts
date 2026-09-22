import languagesJson from '../languages.json';

export interface Language {
  code: LocaleCode;
  name: string;
  native: string;
  script: string;
  dir: 'ltr' | 'rtl';
  bcp47: string;
  bhashini: string;
}

export const LOCALES = ['en', 'hi', 'bn', 'mr', 'te', 'ta', 'gu', 'ur', 'kn', 'or', 'ml', 'pa', 'as'] as const;
export type LocaleCode = (typeof LOCALES)[number];
export const languages = languagesJson as Language[];
export const DEFAULT_LOCALE: LocaleCode = 'en';

export function isLocale(value: string | undefined | null): value is LocaleCode {
  return !!value && (LOCALES as readonly string[]).includes(value);
}

export function languageOf(code: LocaleCode): Language {
  return languages.find((l) => l.code === code) ?? (languages[0] as Language);
}

export type Messages = { [key: string]: string | Messages };

/** Look up "a.b.c" in a nested catalogue; falls back to the key itself so gaps are visible. */
export function lookup(messages: Messages, key: string): string {
  let node: string | Messages | undefined = messages;
  for (const part of key.split('.')) {
    if (!node || typeof node === 'string') return key;
    node = node[part];
  }
  return typeof node === 'string' ? node : key;
}

export function interpolate(template: string, params: Record<string, string | number> = {}): string {
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

/** Indian digit grouping without Intl surprises: 1,25,000. Works on integer rupees. */
export function groupIndian(rupees: number | bigint): string {
  const negative = rupees < 0;
  const digits = (negative ? -BigInt(rupees) : BigInt(rupees)).toString();
  if (digits.length <= 3) return (negative ? '-' : '') + digits;
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',');
  return `${negative ? '-' : ''}${rest},${last3}`;
}

/** ₹ amount from integer paise. Shows paise only when non-zero. */
export function formatPaise(paise: number, opts: { showPaise?: boolean } = {}): string {
  const whole = Math.trunc(paise / 100);
  const frac = Math.abs(paise % 100);
  const base = `₹${groupIndian(whole)}`;
  return opts.showPaise || frac !== 0 ? `${base}.${String(frac).padStart(2, '0')}` : base;
}

export interface UnitWords {
  crore: string;
  lakh: string;
  thousand: string;
  hundred: string;
  rupees: string;
}

/**
 * Speakable amount: "1 lakh 25 thousand rupees" with unit words in the user's language.
 * Digits stay as numerals because every TTS voice reads them natively; the unit words are
 * what people actually say (nobody says "one hundred twenty-five thousand" in a village).
 */
export function amountInWords(paise: number, units: UnitWords): string {
  let rupees = Math.floor(Math.abs(paise) / 100);
  if (rupees === 0) return `0 ${units.rupees}`;
  const parts: string[] = [];
  const take = (size: number, word: string) => {
    const n = Math.floor(rupees / size);
    if (n > 0) {
      parts.push(`${n} ${word}`);
      rupees -= n * size;
    }
  };
  take(10_000_000, units.crore);
  take(100_000, units.lakh);
  take(1_000, units.thousand);
  take(100, units.hundred);
  if (rupees > 0) parts.push(String(rupees));
  return `${parts.join(' ')} ${units.rupees}`;
}

export function unitWordsFrom(messages: Messages): UnitWords {
  return {
    crore: lookup(messages, 'common.crore'),
    lakh: lookup(messages, 'common.lakh'),
    thousand: lookup(messages, 'common.thousand'),
    hundred: lookup(messages, 'common.hundred'),
    rupees: lookup(messages, 'common.rupees'),
  };
}
