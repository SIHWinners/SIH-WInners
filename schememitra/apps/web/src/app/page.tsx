import { getTranslations } from 'next-intl/server';

import { CitizenHeader } from '@/components/citizen-header';
import { Icon, type IconName } from '@/components/icons';
import { ButtonLink } from '@/components/ui';

export default async function HomePage() {
  const t = await getTranslations();
  const how: Array<{ icon: IconName; text: string }> = [
    { icon: 'mic', text: t('home.how_1') },
    { icon: 'scale', text: t('home.how_2') },
    { icon: 'send', text: t('home.how_3') },
  ];
  return (
    <>
      <CitizenHeader />
      <main className="mx-auto flex max-w-3xl flex-col gap-8 px-4 pb-16 pt-8">
        <section className="flex flex-col gap-4">
          <p className="text-sm font-semibold text-accent-ink">{t('common.tagline')}</p>
          <h1 className="text-[1.75rem] font-bold leading-tight sm:text-4xl">{t('home.hero_title')}</h1>
          <p className="text-lg text-muted">{t('home.hero_sub')}</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <ButtonLink href="/apply/voice" size="lg" icon="mic" block>
              {t('home.start_voice')}
            </ButtonLink>
            <ButtonLink href="/apply" size="lg" variant="secondary" icon="doc" block>
              {t('home.start_form')}
            </ButtonLink>
          </div>
        </section>

        <ol className="grid gap-3 sm:grid-cols-3" role="list">
          {how.map((item, i) => (
            <li key={item.icon} className="sm-card flex items-start gap-3 p-4">
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-tint text-brand">
                <Icon name={item.icon} size={22} />
              </span>
              <span className="text-base">
                <span className="sr-only">{i + 1}. </span>
                {item.text}
              </span>
            </li>
          ))}
        </ol>

        <div className="flex flex-wrap gap-3">
          <ButtonLink href="/track" variant="secondary" icon="clock">
            {t('home.track_existing')}
          </ButtonLink>
          <ButtonLink href="/login" variant="ghost" icon="users">
            {t('home.assisted')}
          </ButtonLink>
        </div>

        <footer className="flex flex-col gap-2 border-t border-border pt-4 text-sm text-muted">
          <p className="flex items-center gap-2">
            <Icon name="shield" size={18} /> {t('home.privacy_note')}
          </p>
          <p className="flex items-center gap-2 font-semibold text-success-ink">
            <Icon name="check" size={18} /> {t('common.free_service')}
          </p>
        </footer>
      </main>
    </>
  );
}
