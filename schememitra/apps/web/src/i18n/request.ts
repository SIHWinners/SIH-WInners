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

export default getRequestConfig(async () => {
  const locale = await resolveLocale();
  const messages = (await import(`../../../../packages/i18n/locales/${locale}.json`)).default;
  return { locale, messages, timeZone: 'Asia/Kolkata' };
});
