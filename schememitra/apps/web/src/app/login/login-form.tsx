'use client';

import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Icon } from '@/components/icons';
import { Badge, Button, Card, Field, Notice } from '@/components/ui';
import { useDraft } from '@/stores/draft';

// Demo accounts are fictional and exist only in seeded demo data (see `make seed`).
const DEMO_ACCOUNTS = [
  { phone: '9000000001', label: 'Citizen — Savitaben (Dahod, GJ)', role: 'citizen' },
  { phone: '9000000002', label: 'Citizen — Ramesh (Barmer, RJ)', role: 'citizen' },
  { phone: '9000000010', label: 'CSC operator — Lucknow', role: 'csc_operator' },
  { phone: '9000000020', label: 'Partner officer — Dahod SCA', role: 'partner_officer' },
  { phone: '9000000021', label: 'Partner officer — Barmer SCA', role: 'partner_officer' },
  { phone: '9000000030', label: 'Admin', role: 'admin' },
  { phone: '9000000040', label: 'Policy viewer — MoSJE', role: 'policy_viewer' },
] as const;

const HOME: Record<string, string> = {
  citizen: '/apply',
  csc_operator: '/csc',
  partner_officer: '/partner',
  admin: '/admin',
  policy_viewer: '/insights',
};

export function LoginForm({ initialPhone, next }: { initialPhone: string; next: string | null }) {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [phone, setPhone] = useState(initialPhone);
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'phone' | 'otp'>('phone');
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function requestOtp(target = phone) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/auth/otp/request', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ phone: target }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.user_message_key ?? 'errors.generic');
        return;
      }
      setPhone(target);
      setDevOtp(body.dev_otp ?? null);
      if (body.dev_otp) setCode(body.dev_otp);
      setStep('otp');
    } catch {
      setError('errors.server_down');
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/auth/verify', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ phone, code, lang: locale }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.user_message_key ?? 'errors.generic');
        return;
      }
      // A citizen who applied by voice never typed a phone number: SMS updates go to the one that signed in.
      if (body.user.role === 'citizen') {
        const draft = useDraft.getState();
        if (!draft.personal.phone) draft.setPersonal({ phone: phone.replace(/\D/g, '').slice(-10) });
      }
      router.replace(next && next.startsWith('/') ? next : HOME[body.user.role] ?? '/');
      router.refresh();
    } catch {
      setError('errors.server_down');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void (step === 'phone' ? requestOtp() : verify());
          }}
        >
          {step === 'phone' ? (
            <Field
              label={t('auth.phone')}
              inputMode="numeric"
              autoComplete="tel-national"
              maxLength={14}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              leading={<span className="text-muted">+91</span>}
              data-testid="login-phone"
              required
            />
          ) : (
            <>
              <Field
                label={t('auth.enter_otp')}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                data-testid="login-otp"
                required
                autoFocus
              />
              {devOtp ? (
                <Notice tone="warning" icon="info">
                  {t('auth.dev_otp_note', { otp: devOtp })}
                </Notice>
              ) : null}
            </>
          )}
          {error ? (
            <Notice tone="danger" icon="alert">
              {t(error as 'errors.generic')}
            </Notice>
          ) : null}
          <Button type="submit" size="lg" loading={busy} block icon={step === 'phone' ? 'message' : 'lock'} data-testid="login-submit">
            {step === 'phone' ? t('auth.send_otp') : t('auth.verify')}
          </Button>
          {step === 'otp' ? (
            <Button type="button" variant="ghost" onClick={() => requestOtp()} disabled={busy}>
              {t('auth.resend')}
            </Button>
          ) : null}
        </form>
      </Card>

      <section aria-labelledby="demo-accounts">
        <h2 id="demo-accounts" className="mb-2 flex items-center gap-2 text-sm font-bold text-muted">
          <Icon name="users" size={16} /> {t('auth.demo_accounts')} <Badge tone="warning">DEMO</Badge>
        </h2>
        <ul className="flex flex-col gap-2" role="list">
          {DEMO_ACCOUNTS.map((acc) => (
            <li key={acc.phone}>
              <button
                type="button"
                onClick={() => requestOtp(acc.phone)}
                className="sm-tap flex w-full items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-start hover:border-brand"
              >
                <span className="text-sm font-semibold" lang="en">
                  {acc.label}
                </span>
                <span className="tabular text-xs text-muted">{acc.phone}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
