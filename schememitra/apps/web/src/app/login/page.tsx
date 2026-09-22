import { getTranslations } from 'next-intl/server';

import { CitizenHeader } from '@/components/citizen-header';

import { LoginForm } from './login-form';

export const metadata = { title: 'Sign in' };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ phone?: string; next?: string }> }) {
  const t = await getTranslations('auth');
  const { phone, next } = await searchParams;
  return (
    <>
      <CitizenHeader />
      <main className="mx-auto flex max-w-md flex-col gap-6 px-4 py-8">
        <h1 className="text-2xl font-bold">{t('title')}</h1>
        <LoginForm initialPhone={phone ?? ''} next={next ?? null} />
      </main>
    </>
  );
}
