import { DEFAULT_LOCALE, isLocale, type LocaleCode } from '@sm/i18n';
import { cookies, headers } from 'next/headers';
import { getRequestConfig } from 'next-intl/server';

export const LOCALE_COOKIE = 'sm_locale';

/** Locale comes from the cookie set by the language picker, else the browser's first
 * supported language, else English. No locale in the URL keeps links shareable by SMS. */
export async function resolveLocale(): Promise<LocaleCode> {
  const fromCookie = (await cookies()).get(LOCALE_COOKIE)?.value;
  if (isLocale(fromCookie)) return fromCookie;
  const accept = (await headers()).get('accept-language') ?? '';
  for (const part of accept.split(',')) {
    const code = part.split(';')[0]?.trim().slice(0, 2).toLowerCase();
    if (isLocale(code)) return code;
  }
  return DEFAULT_LOCALE;
}

type Messages = Record<string, unknown>;

/** English underneath every locale. Citizen strings are translated into all 13 languages, but
 * officer-facing screens are English + Hindi only (ADR-012); without a base, a partner officer
 * or CSC operator whose phone is set to, say, Urdu would see raw message keys. */
function withEnglishBase(base: Messages, locale: Messages): Messages {
  const out: Messages = { ...base };
  for (const [key, value] of Object.entries(locale)) {
    const current = out[key];
    out[key] =
      value && typeof value === 'object' && !Array.isArray(value) && current && typeof current === 'object'
        ? withEnglishBase(current as Messages, value as Messages)
        : value;
  }
  return out;
}

export default getRequestConfig(async () => {
  const locale = await resolveLocale();
  const english = (await import('../../../../packages/i18n/locales/en.json')).default as Messages;
  const messages =
    locale === 'en'
      ? english
      : withEnglishBase(english, (await import(`../../../../packages/i18n/locales/${locale}.json`)).default as Messages);
  return { locale, messages, timeZone: 'Asia/Kolkata' };
});
