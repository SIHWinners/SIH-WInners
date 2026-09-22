'use client';

import { languageOf, type LocaleCode } from '@sm/i18n';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { useCallback, useEffect, useState, type ReactNode } from 'react';

import { CitizenHeader } from '@/components/citizen-header';
import { Icon } from '@/components/icons';
import { cx } from '@/components/ui';

export const STEPS = [
  { key: 'speak_scan', href: '/apply', icon: 'mic' },
  { key: 'rule_check', href: '/apply/rules', icon: 'scale' },
  { key: 'money_maths', href: '/apply/money', icon: 'rupee' },
  { key: 'partner_pick', href: '/apply/partner', icon: 'pin' },
  { key: 'send_track', href: '/apply/send', icon: 'send' },
] as const;

export type StepKey = (typeof STEPS)[number]['key'];

export function Stepper({ current, reachable }: { current: StepKey; reachable: number }) {
  const t = useTranslations();
  const index = STEPS.findIndex((s) => s.key === current);
  return (
    <nav aria-label={t('common.step_of', { current: index + 1, total: STEPS.length })} className="mx-auto max-w-3xl px-4 pt-4">
      <p className="mb-2 text-sm font-semibold text-muted">
        {t('common.step_of', { current: index + 1, total: STEPS.length })} · <span className="text-text">{t(`steps.${current}`)}</span>
      </p>
      <ol className="grid grid-cols-5 gap-1.5" role="list">
        {STEPS.map((step, i) => {
          const done = i < index;
          const active = i === index;
          const body = (
            <>
              <span
                className={cx(
                  'block h-1.5 rounded-full transition-colors',
                  done ? 'bg-success' : active ? 'bg-accent' : 'bg-border',
                )}
              />
              <span className={cx('mt-1.5 flex items-center gap-1 text-xs max-sm:sr-only', active ? 'font-bold text-text' : 'text-muted')}>
                {done ? <Icon name="check" size={14} className="text-success-ink" /> : null}
                {t(`steps.${step.key}`)}
              </span>
            </>
          );
          return (
            <li key={step.key} aria-current={active ? 'step' : undefined}>
              {i <= reachable && !active ? (
                <Link href={step.href} className="block rounded">
                  {body}
                </Link>
              ) : (
                <span className="block">{body}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function NextStepCard({ step, extra }: { step: StepKey | 'submitted'; extra?: Record<string, string | number> }) {
  const t = useTranslations('next_card');
  return (
    <aside className="flex gap-3 rounded-xl border border-brand/20 bg-brand-tint p-4 text-brand-ink" aria-live="polite">
      <Icon name="chevronRight" size={22} className="mt-0.5 shrink-0 rtl:rotate-180" />
      <div>
        <p className="text-sm font-bold">{t('title')}</p>
        <p className="text-sm">{t(step, extra as never)}</p>
      </div>
    </aside>
  );
}

let currentAudio: HTMLAudioElement | null = null;

export function stopSpeaking() {
  currentAudio?.pause();
  currentAudio = null;
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel();
}

/**
 * Speaks a reply: the server clip (pre-generated or Bhashini TTS) when there is one, else the
 * device voice (spec §13: clips → device TTS). Resolves when playback ends.
 */
export function speakText(text: string, locale: LocaleCode, audioUrl?: string | null): Promise<void> {
  stopSpeaking();
  return new Promise((resolve) => {
    if (audioUrl) {
      const audio = new Audio(`/api${audioUrl}`);
      currentAudio = audio;
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
      audio.play().catch(() => resolve());
      return;
    }
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return resolve();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = languageOf(locale).bcp47;
    utterance.rate = 0.92;
    utterance.onend = () => resolve();
    utterance.onerror = () => resolve();
    window.speechSynthesis.speak(utterance);
  });
}

/** Reads text aloud: server clip first, device voice as the fallback. */
export function ListenButton({ text, audioUrl, className }: { text: string; audioUrl?: string | null; className?: string }) {
  const t = useTranslations('common');
  const locale = useLocale() as LocaleCode;
  const [speaking, setSpeaking] = useState(false);
  // Decided after mount so server and client render the same markup.
  const [supported, setSupported] = useState(false);
  useEffect(() => setSupported(Boolean(audioUrl) || 'speechSynthesis' in window), [audioUrl]);

  const speak = useCallback(() => {
    if (speaking) {
      stopSpeaking();
      setSpeaking(false);
      return;
    }
    setSpeaking(true);
    void speakText(text, locale, audioUrl).then(() => setSpeaking(false));
  }, [audioUrl, locale, speaking, text]);

  useEffect(() => () => stopSpeaking(), []);

  if (!supported) return null;
  return (
    <button
      type="button"
      onClick={speak}
      className={cx(
        'sm-tap inline-flex shrink-0 items-center justify-center gap-1.5 rounded-full border px-3 text-sm font-semibold',
        speaking ? 'border-accent bg-accent-tint text-accent-ink' : 'border-border-strong text-brand hover:bg-brand-tint',
        className,
      )}
      aria-pressed={speaking}
    >
      <Icon name={speaking ? 'stop' : 'speaker'} size={18} />
      {speaking ? t('stop') : t('listen')}
    </button>
  );
}

export function OfflineBanner() {
  const t = useTranslations('common');
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);
  if (online) return null;
  return (
    <div role="status" className="flex items-center gap-2 bg-warning-tint px-4 py-2 text-sm font-semibold text-warning-ink">
      <Icon name="wifiOff" size={18} /> {t('offline_banner')}
    </div>
  );
}

export function ApplyShell({ step, reachable, children, footer }: { step: StepKey; reachable: number; children: ReactNode; footer?: ReactNode }) {
  return (
    <>
      <CitizenHeader />
      <OfflineBanner />
      <Stepper current={step} reachable={reachable} />
      <main className="mx-auto flex max-w-3xl flex-col gap-5 px-4 pb-32 pt-5">{children}</main>
      {footer ? (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 backdrop-blur">
          <div className="mx-auto flex max-w-3xl gap-3 px-4 py-3">{footer}</div>
        </div>
      ) : null}
    </>
  );
}
