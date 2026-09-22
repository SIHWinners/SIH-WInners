'use client';

import type { ApplicantFacts, components } from '@sm/contracts/client';
import type { LocaleCode } from '@sm/i18n';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

import { Icon } from '@/components/icons';
import { Badge, Button, Card, cx, Notice, SandboxBadge, Skeleton } from '@/components/ui';
import { ApiError } from '@/lib/api';
import { evaluateFacts } from '@/lib/evaluate';
import { useRecorder } from '@/lib/recorder';
import { useDraft } from '@/stores/draft';

import { visibleQuestions } from './questions';
import { ApplyShell, ListenButton, NextStepCard, speakText, stopSpeaking } from './shell';

type Turn = components['schemas']['VoiceTurnOut'];
interface ChatLine {
  role: 'assistant' | 'user';
  text: string;
  audioUrl?: string | null;
  engine?: Turn['transcript_engine'];
}

const PANEL_FIELDS = [
  'full_name', 'age', 'district_code', 'gender', 'social_category', 'has_disability', 'disability_pct', 'business_type',
  'course_admitted', 'project_cost_paise', 'loan_needed_paise', 'annual_family_income_paise', 'education_level',
  'shg_member', 'existing_loans', 'state_code', 'pincode',
] as const;
const SESSION_KEY = 'sm-voice-session';

async function post(path: string, body: FormData | object): Promise<Turn> {
  const isForm = body instanceof FormData;
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    body: isForm ? body : JSON.stringify(body),
    headers: isForm ? undefined : { 'content-type': 'application/json' },
  });
  const json = await res.json();
  if (!res.ok) throw new ApiError(json);
  return json as Turn;
}

function formatClock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Applies spoken answers to the same draft the typed form uses, so either path can finish. */
function applySlots(turn: Turn) {
  const draft = useDraft.getState();
  const facts: Partial<ApplicantFacts> = {};
  for (const [name, slot] of Object.entries(turn.slots)) {
    if (name === 'full_name') draft.setPersonal({ full_name: String(slot.value) });
    else (facts as Record<string, unknown>)[name] = slot.value;
  }
  if (turn.district_hq) {
    facts.lat = turn.district_hq.lat;
    facts.lng = turn.district_hq.lng;
    facts.pincode = (facts.pincode as string | undefined) ?? draft.facts.pincode ?? turn.district_hq.pincode;
  }
  draft.setFacts(facts);
}

export function VoiceFlow() {
  const t = useTranslations();
  const locale = useLocale() as LocaleCode;
  const router = useRouter();
  const hydrated = useDraft((s) => s.hydrated);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [finishedAt, setFinishedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const logRef = useRef<HTMLOListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const receive = useCallback(
    (next: Turn, userLine?: ChatLine) => {
      setTurn(next);
      setLines((prev) => [...prev, ...(userLine ? [userLine] : []), { role: 'assistant', text: next.reply_text, audioUrl: next.reply_audio_url }]);
      applySlots(next);
      if (next.state === 'done') setFinishedAt((f) => f ?? Date.now());
      if (autoSpeak) void speakText(next.reply_text, locale, next.reply_audio_url);
    },
    [autoSpeak, locale],
  );

  const startSession = useCallback(async () => {
    setError(null);
    setLines([]);
    setFinishedAt(null);
    try {
      const first = await post('/v1/voice/sessions', { lang: locale });
      sessionStorage.setItem(SESSION_KEY, first.session_id);
      useDraft.getState().setMode('voice');
      setStartedAt(Date.now());
      receive(first);
    } catch (err) {
      setError(err instanceof ApiError ? err.problem.user_message_key : 'errors.network');
    }
  }, [locale, receive]);

  useEffect(() => {
    if (!hydrated || turn) return;
    void startSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated]);

  useEffect(() => {
    if (!startedAt || finishedAt) return;
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [startedAt, finishedAt]);

  useEffect(() => {
    logRef.current?.lastElementChild?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [lines.length]);

  const send = useCallback(
    async (input: { text?: string; audio?: Blob }, shown?: string) => {
      if (!turn || busy) return;
      stopSpeaking();
      setBusy(true);
      setError(null);
      const form = new FormData();
      if (input.text) form.set('text', input.text);
      if (input.audio) form.set('audio', input.audio, `utterance.${input.audio.type.includes('mp4') ? 'm4a' : 'webm'}`);
      try {
        const next = await post(`/v1/voice/sessions/${turn.session_id}/utterance`, form);
        receive(next, { role: 'user', text: shown ?? next.transcript ?? input.text ?? '', engine: next.transcript_engine });
        setTyped('');
      } catch (err) {
        const key = err instanceof ApiError ? err.problem.user_message_key : 'errors.network';
        setError(key);
        if (key === 'voice.asr_unavailable') inputRef.current?.focus();
      } finally {
        setBusy(false);
      }
    },
    [busy, receive, turn],
  );

  const recorder = useRecorder((audio) => void send({ audio }));

  async function finish(target: 'rules' | 'form') {
    setFinishing(true);
    const draft = useDraft.getState();
    try {
      if (target === 'rules') {
        draft.setEvaluation(await evaluateFacts(draft.facts));
        router.push('/apply/rules');
      } else {
        const questions = visibleQuestions(draft.facts);
        const firstOpen = questions.findIndex((q) =>
          q.target.scope === 'personal' ? !draft.personal[q.target.key] : draft.facts[q.target.key] === undefined,
        );
        draft.setIntakeIndex(Math.max(0, firstOpen));
        router.push('/apply');
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.problem.user_message_key : 'errors.generic');
      setFinishing(false);
    }
  }

  if (!hydrated || (!turn && !error)) {
    return (
      <ApplyShell step="speak_scan" reachable={0}>
        <Skeleton className="h-72" />
      </ApplyShell>
    );
  }

  const listening = recorder.state === 'listening';
  const done = turn?.state === 'done';
  const chips = turn?.demo_utterances ?? [];
  const nextChip = turn && !done && chips.length ? chips[turn.state === 'confirm' ? chips.length - 1 : Math.min(turn.turn, chips.length - 1)] : undefined;
  const elapsed = startedAt ? (finishedAt ?? now) - startedAt : 0;
  const lastUser = [...lines].reverse().find((l) => l.role === 'user');
  const micDisabled = busy || done || recorder.state === 'unsupported' || !turn?.asr_available;

  return (
    <ApplyShell
      step="speak_scan"
      reachable={0}
      footer={
        done ? (
          <Button size="lg" block iconRight="chevronRight" loading={finishing} onClick={() => finish(turn!.handoff === 'form' ? 'form' : 'rules')}
            data-testid="voice-finish">
            {turn!.handoff === 'form' ? t('voice.fill_rest') : t('voice.see_schemes')}
          </Button>
        ) : undefined
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{t('voice.title')}</h1>
        <div className="flex items-center gap-2">
          <Badge tone={done ? 'success' : 'brand'} icon="clock" data-testid="voice-timer">
            {t('voice.timer', { time: formatClock(elapsed) })}
          </Badge>
          {turn ? <Badge tone="neutral">{t('voice.turns', { turn: turn.turn, max: turn.max_turns })}</Badge> : null}
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-3 sm:p-4">
            <ol ref={logRef} className="flex max-h-[46vh] min-h-40 flex-col gap-3 overflow-y-auto pe-1" aria-live="polite" data-testid="voice-log">
              {lines.map((line, i) => (
                <li key={i} className={cx('sm-enter flex max-w-[92%] flex-col gap-1', line.role === 'user' ? 'self-end items-end' : 'self-start')}>
                  <div
                    className={cx(
                      'rounded-2xl px-3.5 py-2.5 text-base leading-relaxed',
                      line.role === 'user' ? 'rounded-br-sm bg-brand text-on-brand' : 'rounded-bl-sm bg-brand-tint text-text',
                    )}
                    data-testid={line.role === 'user' ? 'voice-user-line' : 'voice-reply'}
                  >
                    {line.text}
                  </div>
                  {line.role === 'assistant' && i === lines.length - 1 ? (
                    <ListenButton text={line.text} audioUrl={line.audioUrl} className="h-9 self-start" />
                  ) : null}
                  {line.role === 'user' && line.engine === 'sandbox' ? <SandboxBadge label={`SANDBOX · ${t('voice.you_said')}`} /> : null}
                </li>
              ))}
              {busy ? (
                <li className="self-end text-sm font-semibold text-muted" role="status">
                  {t('voice.thinking')}
                </li>
              ) : null}
            </ol>

            {turn?.clarify && !busy ? (
              <div className="flex flex-wrap gap-2" data-testid="voice-clarify">
                <Button variant="success" icon="check" onClick={() => send({ text: 'yes' }, t('common.yes'))}>{t('common.yes')}</Button>
                <Button variant="secondary" icon="x" onClick={() => send({ text: 'no' }, t('common.no'))}>{t('common.no')}</Button>
              </div>
            ) : null}
            {turn?.state === 'confirm' && !busy ? (
              <div className="flex flex-wrap gap-2">
                <Button variant="success" icon="check" onClick={() => send({ text: 'yes' }, t('common.yes'))} data-testid="voice-confirm-yes">
                  {t('common.yes')}
                </Button>
              </div>
            ) : null}

            {!done ? (
              <div className="flex flex-col items-center gap-2 border-t border-border pt-3">
                <button
                  type="button"
                  onClick={() => {
                    setAutoSpeak(true);
                    if (listening) recorder.stop();
                    else void recorder.start();
                  }}
                  disabled={micDisabled}
                  aria-pressed={listening}
                  data-testid="voice-mic"
                  className={cx(
                    'relative grid size-20 place-items-center rounded-full text-on-brand shadow-md transition-transform disabled:opacity-50',
                    listening ? 'bg-danger scale-105' : 'bg-brand hover:bg-brand-ink',
                  )}
                  style={listening ? { boxShadow: `0 0 0 ${4 + recorder.level * 18}px color-mix(in srgb, var(--sm-danger) 25%, transparent)` } : undefined}
                >
                  <Icon name={listening ? 'stop' : 'mic'} size={34} />
                  <span className="sr-only">{listening ? t('common.stop') : t('voice.tap_to_speak')}</span>
                </button>
                <p className="text-sm font-semibold text-muted" role="status">
                  {listening ? t('voice.listening') : busy ? t('voice.thinking') : t('voice.tap_to_speak')}
                </p>
                {recorder.state === 'blocked' ? <Notice tone="warning" icon="alert">{t('voice.mic_blocked')}</Notice> : null}
              </div>
            ) : null}

            {!done ? (
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (typed.trim()) void send({ text: typed.trim() });
                }}
              >
                <label htmlFor="voice-typed" className="sr-only">{t('voice.type_placeholder')}</label>
                <input
                  id="voice-typed"
                  ref={inputRef}
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  placeholder={t('voice.type_placeholder')}
                  className="sm-tap min-w-0 flex-1 rounded-md border border-border-strong bg-surface px-3 text-base"
                  data-testid="voice-typed"
                  disabled={busy}
                />
                <Button type="submit" icon="send" disabled={busy || !typed.trim()} aria-label={t('voice.send')}>
                  <span className="max-sm:sr-only">{t('voice.send')}</span>
                </Button>
              </form>
            ) : null}

            {error ? <Notice tone={error === 'voice.asr_unavailable' ? 'warning' : 'danger'} icon="alert">{t(error as never)}</Notice> : null}
          </Card>

          {nextChip ? (
            <section className="flex flex-col gap-2" aria-labelledby="demo-chips">
              <h2 id="demo-chips" className="flex items-center gap-2 text-sm font-semibold text-muted">
                {t('voice.demo_chips')} <SandboxBadge />
              </h2>
              <button
                type="button"
                disabled={busy}
                onClick={() => send({ text: nextChip })}
                className="sm-tap rounded-xl border border-dashed border-brand/40 bg-surface px-3 py-2 text-start text-base hover:bg-brand-tint disabled:opacity-60"
                data-testid="voice-demo-chip"
              >
                “{nextChip}”
              </button>
            </section>
          ) : null}

          {lastUser?.engine === 'sandbox' ? <p className="text-xs text-muted">{t('voice.sandbox_transcript')}</p> : null}
          {turn?.tts === 'device' ? (
            <p className="flex items-center gap-1.5 text-xs text-muted">
              <Icon name="speaker" size={14} /> {t('voice.device_voice')}
            </p>
          ) : null}
        </div>

        <FormPanel turn={turn} />
      </div>

      {done ? null : (
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" icon="refresh" onClick={() => void startSession()}>
            {t('voice.restart')}
          </Button>
        </div>
      )}
      <NextStepCard step="speak_scan" />
    </ApplyShell>
  );
}

function FormPanel({ turn }: { turn: Turn | null }) {
  const t = useTranslations();
  const slots = turn?.slots ?? {};
  const visible = PANEL_FIELDS.filter(
    (f) => (f !== 'disability_pct' || slots.has_disability?.value === true) && (f !== 'course_admitted' || slots.business_type?.value === 'education')
      && (f !== 'pincode' || slots.pincode) && (f !== 'state_code' || slots.state_code),
  );
  return (
    <aside className="flex flex-col gap-3 md:sticky md:top-4 md:self-start" aria-labelledby="form-panel-title" data-testid="voice-form-panel">
      <div>
        <h2 id="form-panel-title" className="text-lg font-bold">{t('voice.form_panel')}</h2>
        <p className="text-sm text-muted" data-testid="voice-filled">
          {t('intake.fields_filled', { filled: turn?.filled ?? 0, total: turn?.total ?? 13 })}
        </p>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-border" aria-hidden>
          <div className="h-full rounded-full bg-success transition-[width] duration-500" style={{ width: `${turn ? (100 * turn.filled) / Math.max(1, turn.total) : 0}%` }} />
        </div>
      </div>
      <dl className="grid grid-cols-1 gap-1.5">
        {visible.map((field) => {
          const slot = slots[field];
          const changed = turn?.changed?.includes(field);
          const pending = turn?.clarify?.slot === field;
          return (
            <div
              key={field}
              className={cx(
                'flex items-baseline justify-between gap-3 rounded-lg border px-3 py-2',
                slot ? 'border-success/40 bg-success-tint' : pending ? 'border-warning bg-warning-tint' : 'border-border bg-surface',
                changed && 'sm-enter',
              )}
              data-testid={`voice-field-${field}`}
              data-filled={slot ? 'true' : 'false'}
            >
              <dt className="text-sm text-muted first-letter:uppercase">{t(`voice.field.${field}` as never)}</dt>
              <dd className={cx('text-end text-sm font-semibold', slot ? 'text-text' : 'text-muted')}>
                {slot ? (
                  <span className="inline-flex items-center gap-1">
                    {slot.method === 'llm' ? <Icon name="sparkle" size={14} className="text-accent-ink" /> : <Icon name="check" size={14} className="text-success-ink" />}
                    {slot.display}
                  </span>
                ) : pending ? (
                  turn?.clarify?.display
                ) : (
                  '—'
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </aside>
  );
}
