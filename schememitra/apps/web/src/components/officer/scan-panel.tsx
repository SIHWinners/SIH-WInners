'use client';

import type { components } from '@sm/contracts/client';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

import { Icon } from '@/components/icons';
import { Button, Card, Notice } from '@/components/ui';
import { api, ApiError, unwrap } from '@/lib/api';

type Scan = components['schemas']['ScanOut'];

interface BarcodeDetectorLike {
  detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]>;
}
type BarcodeDetectorCtor = new (options: { formats: string[] }) => BarcodeDetectorLike;

/**
 * Verifies the citizen's signed QR (Ed25519 JWS) and opens the file. The QR carries no personal
 * data — only a tracking id, a file hash and the lender it was addressed to — so the server checks
 * the signature and that this lender is the addressee before anything is shown.
 */
export function ScanPanel() {
  const t = useTranslations();
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [scanning, setScanning] = useState(false);
  const [pasted, setPasted] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Scan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cameraSupported = typeof window !== 'undefined' && 'BarcodeDetector' in window && Boolean(navigator.mediaDevices);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setScanning(false);
  }, []);

  useEffect(() => stop, [stop]);

  const verify = useCallback(
    async (jws: string) => {
      setBusy(true);
      setError(null);
      try {
        const out = await unwrap(api.POST('/v1/partner/scan', { body: { jws: jws.trim() } }));
        setResult(out);
        stop();
        setTimeout(() => router.push(`/partner/applications/${out.application_id}`), 900);
      } catch (err) {
        setError(err instanceof ApiError ? err.problem.user_message_key : 'errors.network');
      } finally {
        setBusy(false);
      }
    },
    [router, stop],
  );

  async function startCamera() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      streamRef.current = stream;
      setScanning(true);
      const video = videoRef.current!;
      video.srcObject = stream;
      await video.play();
      const Detector = (window as unknown as { BarcodeDetector: BarcodeDetectorCtor }).BarcodeDetector;
      const detector = new Detector({ formats: ['qr_code'] });
      const tick = async () => {
        if (!streamRef.current) return;
        try {
          const codes = await detector.detect(video);
          if (codes.length > 0 && codes[0]!.rawValue) {
            await verify(codes[0]!.rawValue);
            return;
          }
        } catch {
          /* frame not ready */
        }
        requestAnimationFrame(() => void tick());
      };
      void tick();
    } catch {
      setError('officer.scan.no_camera');
      setScanning(false);
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Card className="flex flex-col gap-3">
        <p className="text-muted">{t('officer.scan.camera')}</p>
        <div className="relative overflow-hidden rounded-lg border border-border bg-surface-alt">
          {/* The camera feed is a scanner viewfinder, not media content: nothing to caption. */}
          <video ref={videoRef} className={scanning ? 'aspect-video w-full object-cover' : 'hidden'} playsInline muted />
          {!scanning ? (
            <div className="grid aspect-video w-full place-items-center text-muted">
              <Icon name="qr" size={48} />
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {cameraSupported ? (
            <Button icon={scanning ? 'stop' : 'camera'} onClick={() => (scanning ? stop() : void startCamera())} data-testid="scan-camera">
              {scanning ? t('officer.scan.stop_camera') : t('officer.scan.start_camera')}
            </Button>
          ) : (
            <Notice tone="warning" icon="info">{t('officer.scan.no_camera')}</Notice>
          )}
        </div>
      </Card>

      <Card className="flex flex-col gap-3">
        <label htmlFor="scan-paste" className="font-semibold">{t('officer.scan.paste_label')}</label>
        <textarea
          id="scan-paste"
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          rows={3}
          className="w-full rounded-md border border-border-strong bg-surface p-2 font-mono text-xs"
          data-testid="scan-paste"
        />
        <Button icon="qr" loading={busy} disabled={pasted.trim().length < 20} onClick={() => void verify(pasted)} data-testid="scan-verify">
          {t('officer.scan.verify')}
        </Button>
        {error ? <Notice tone="danger" icon="alert">{t(error as never)}</Notice> : null}
        {result ? (
          <div className="flex flex-col gap-1 text-sm" role="status" data-testid="scan-result">
            <p className="flex items-center gap-2 font-semibold text-success-ink">
              <Icon name="check" size={16} /> {t('officer.scan.verified')} · {result.tracking_id}
            </p>
            <p className={result.file_unchanged ? 'text-muted' : 'font-semibold text-warning-ink'}>
              {result.file_unchanged ? t('officer.scan.unchanged') : t('officer.scan.changed')}
            </p>
            {result.received_now ? <p className="text-muted">{t('officer.scan.received')}</p> : null}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
