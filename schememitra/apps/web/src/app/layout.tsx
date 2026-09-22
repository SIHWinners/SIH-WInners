import { languageOf } from '@sm/i18n';
import type { Metadata, Viewport } from 'next';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages, getTranslations } from 'next-intl/server';
import type { ReactNode } from 'react';

import { resolveLocale } from '@/i18n/request';

import { fontStackFor, latinFontClass } from './fonts';
import './globals.css';

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('common');
  return {
    title: { default: `SchemeMitra — ${t('tagline')}`, template: '%s · SchemeMitra' },
    description: t('tagline'),
    manifest: '/manifest.webmanifest',
    applicationName: 'SchemeMitra',
    icons: { icon: '/icon.svg', apple: '/icon-192.png' },
  };
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#0B3D91' },
    { media: '(prefers-color-scheme: dark)', color: '#0B1220' },
  ],
};

// Runs before first paint so theme, contrast and text size never flash. Values come from
// localStorage and are validated against an allow-list before touching the DOM.
const PREFS_SCRIPT = `try{var d=document.documentElement,s=localStorage;var t=s.getItem('sm_theme');if(t==='dark'||t==='light')d.dataset.theme=t;if(s.getItem('sm_contrast')==='high')d.dataset.contrast='high';if(s.getItem('sm_text')==='large')d.dataset.textSize='large';}catch(e){}`;

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await resolveLocale();
  const messages = await getMessages();
  const lang = languageOf(locale);
  return (
    <html
      lang={lang.bcp47}
      dir={lang.dir}
      className={latinFontClass}
      style={{ ['--sm-font' as string]: fontStackFor(locale) }}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: PREFS_SCRIPT }} />
      </head>
      <body className="min-h-dvh antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
