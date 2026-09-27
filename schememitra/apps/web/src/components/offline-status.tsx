'use client';

import { useTranslations } from 'next-intl';
import { useEffect, useState } from 'react';

import { Icon } from '@/components/icons';
import { Button, cx } from '@/components/ui';
import { refreshRulesBundle } from '@/lib/evaluate';
import { flushOutbox, startSync, subscribeToSync, type SyncState } from '@/lib/sync';

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/**
 * One small bar that tells the truth about the connection: what is still on this phone,
 * whether it is being sent, and — when the browser offers it — how to install the app so it
 * opens without a data connection.
 */
export function OfflineStatus() {
  const t = useTranslations();
  const [online, setOnline] = useState(true);
  const [sync, setSync] = useState<SyncState>({ pending: 0, syncing: false, lastError: null });
  const [installer, setInstaller] = useState<InstallPromptEvent | null>(null);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    const unsubscribe = subscribeToSync(setSync);
    const stopSync = startSync();
    // Keep the offline rule bundle and district list fresh while there is a connection, so the
    // next visit works on a dead cell (claims C13, C14). A 304 costs a few hundred bytes.
    void refreshRulesBundle();
    const onInstall = (event: Event) => {
      event.preventDefault();
      setInstaller(event as InstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', onInstall);
    window.addEventListener('appinstalled', () => setInstaller(null));
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
      window.removeEventListener('beforeinstallprompt', onInstall);
      unsubscribe();
      stopSync();
    };
  }, []);

  if (online && sync.pending === 0 && !installer) return null;

  return (
    <div
      role="status"
      data-testid="offline-status"
      className={cx(
        'flex flex-wrap items-center gap-2 px-4 py-2 text-sm font-semibold',
        online ? 'bg-brand-tint text-brand-ink' : 'bg-warning-tint text-warning-ink',
      )}
    >
      {!online ? (
        <>
          <Icon name="wifiOff" size={18} /> {t('common.offline_banner')}
        </>
      ) : sync.pending > 0 ? (
        <>
          <Icon name="refresh" size={18} className={sync.syncing ? 'animate-spin' : undefined} />
          {t('offline.will_sync')} <span className="tabular" data-testid="outbox-count">{sync.pending}</span>
        </>
      ) : null}

      {sync.pending > 0 && online ? (
        <Button size="sm" variant="ghost" onClick={() => void flushOutbox()} data-testid="sync-now">
          {t('common.retry')}
        </Button>
      ) : null}

      {installer ? (
        <Button
          size="sm"
          variant="secondary"
          icon="download"
          className="ms-auto"
          data-testid="install-app"
          onClick={async () => {
            await installer.prompt();
            await installer.userChoice;
            setInstaller(null);
          }}
        >
          {t('home.install_app')}
        </Button>
      ) : null}
    </div>
  );
}
