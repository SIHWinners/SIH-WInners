'use client';

import { languages, type LocaleCode } from '@sm/i18n';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { useEffect, useRef, useState, useTransition } from 'react';

import { Icon } from './icons';
import { Wordmark } from './logo';
import { cx } from './ui';

type Pref = 'sm_theme' | 'sm_contrast' | 'sm_text';

function writePref(key: Pref, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* private mode: preference simply won't persist */
  }
}

export function CitizenHeader() {
  const t = useTranslations('common');
  const locale = useLocale() as LocaleCode;
  const [langOpen, setLangOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [prefs, setPrefs] = useState({ dark: false, contrast: false, large: false });
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = document.documentElement.dataset;
    setPrefs({ dark: d.theme === 'dark', contrast: d.contrast === 'high', large: d.textSize === 'large' });
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (langOpen && !dialog.open) dialog.showModal();
    if (!langOpen && dialog.open) dialog.close();
  }, [langOpen]);

  function toggle(kind: 'dark' | 'contrast' | 'large') {
    const next = { ...prefs, [kind]: !prefs[kind] };
    setPrefs(next);
    const d = document.documentElement.dataset;
    if (kind === 'dark') {
      d.theme = next.dark ? 'dark' : 'light';
      writePref('sm_theme', d.theme);
    } else if (kind === 'contrast') {
      if (next.contrast) d.contrast = 'high';
      else delete d.contrast;
      writePref('sm_contrast', next.contrast ? 'high' : null);
    } else {
      if (next.large) d.textSize = 'large';
      else delete d.textSize;
      writePref('sm_text', next.large ? 'large' : null);
    }
  }

  async function chooseLanguage(code: LocaleCode) {
    await fetch('/api/locale', { method: 'POST', body: JSON.stringify({ locale: code }) });
    setLangOpen(false);
    // Full reload so fonts, dir and server-rendered text all switch together.
    startTransition(() => window.location.reload());
  }

  const current = languages.find((l) => l.code === locale);

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-3xl items-center gap-2 px-4">
        <Link href="/" className="mr-auto rounded-md" aria-label="SchemeMitra">
          <Wordmark size={28} />
        </Link>
        <button
          type="button"
          onClick={() => setLangOpen(true)}
          className="sm-tap inline-flex items-center gap-1.5 rounded-md px-2 text-sm font-semibold text-brand hover:bg-brand-tint"
          aria-haspopup="dialog"
        >
          <Icon name="globe" size={20} />
          <span>{current?.native}</span>
          <span className="sr-only">— {t('change_language')}</span>
        </button>
        <PrefButton label={t('text_size')} active={prefs.large} icon="text" onClick={() => toggle('large')} />
        <PrefButton label={t('high_contrast')} active={prefs.contrast} icon="contrast" onClick={() => toggle('contrast')} />
        <PrefButton label={t('dark_mode')} active={prefs.dark} icon="moon" onClick={() => toggle('dark')} />
      </div>

      <dialog
        ref={dialogRef}
        onClose={() => setLangOpen(false)}
        className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-border bg-surface p-0 text-text backdrop:bg-black/40"
        aria-labelledby="lang-title"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 id="lang-title" className="text-lg font-bold">
            {t('change_language')}
          </h2>
          <button type="button" onClick={() => setLangOpen(false)} className="sm-tap grid place-items-center rounded-md hover:bg-surface-alt" aria-label={t('close')}>
            <Icon name="x" />
          </button>
        </div>
        <ul className="grid grid-cols-2 gap-2 p-4" role="list">
          {languages.map((lang) => (
            <li key={lang.code}>
              <button
                type="button"
                lang={lang.bcp47}
                dir={lang.dir}
                disabled={pending}
                onClick={() => chooseLanguage(lang.code)}
                className={cx(
                  'sm-tap flex w-full flex-col items-start rounded-lg border px-3 py-2 text-start',
                  lang.code === locale ? 'border-brand bg-brand-tint' : 'border-border hover:border-brand',
                )}
                aria-current={lang.code === locale ? 'true' : undefined}
              >
                <span className="text-base font-semibold">{lang.native}</span>
                <span className="text-xs text-muted" lang="en">
                  {lang.name}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </dialog>
    </header>
  );
}

function PrefButton({ label, active, icon, onClick }: { label: string; active: boolean; icon: 'text' | 'contrast' | 'moon'; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={label}
      className={cx('sm-tap grid place-items-center rounded-md', active ? 'bg-brand text-on-brand' : 'text-muted hover:bg-surface-alt')}
    >
      <Icon name={icon} size={20} />
      <span className="sr-only">{label}</span>
    </button>
  );
}
