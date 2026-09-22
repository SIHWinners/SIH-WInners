'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type RecorderState = 'idle' | 'listening' | 'unsupported' | 'blocked';

const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm', 'audio/mp4'];

/**
 * Short-utterance recorder: 16 kHz mono Opus at ~12 kbps where the browser allows, stops
 * itself after `silenceMs` of quiet once speech was heard (a simple energy VAD) or at
 * `maxMs` (15 s chunks, spec §9.1). Audio stays in memory and is handed to `onDone`.
 */
export function useRecorder(onDone: (audio: Blob) => void, { maxMs = 15_000, silenceMs = 1_300 } = {}) {
  const [state, setState] = useState<RecorderState>('idle');
  const [level, setLevel] = useState(0);
  const stopRef = useRef<() => void>(() => undefined);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    if (typeof window !== 'undefined' && (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined')) {
      setState('unsupported');
    }
    return () => stopRef.current();
  }, []);

  const start = useCallback(async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: 16_000, echoCancellation: true, noiseSuppression: true },
      });
    } catch {
      setState('blocked');
      return;
    }
    const mimeType = MIME_TYPES.find((m) => MediaRecorder.isTypeSupported(m));
    const recorder = new MediaRecorder(stream, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 12_000 });
    const chunks: Blob[] = [];
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    let heardSpeech = false;
    let quietSince = performance.now();
    let frame = 0;
    const startedAt = performance.now();

    const cleanup = () => {
      cancelAnimationFrame(frame);
      stream.getTracks().forEach((track) => track.stop());
      void ctx.close();
      setLevel(0);
    };
    const tick = () => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const s of samples) sum += ((s - 128) / 128) ** 2;
      const rms = Math.sqrt(sum / samples.length);
      setLevel(Math.min(1, rms * 6));
      const now = performance.now();
      if (rms > 0.04) {
        heardSpeech = true;
        quietSince = now;
      }
      if ((heardSpeech && now - quietSince > silenceMs) || now - startedAt > maxMs) {
        stop();
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    const stop = () => {
      if (recorder.state !== 'inactive') recorder.stop();
    };

    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      cleanup();
      setState('idle');
      const blob = new Blob(chunks, { type: (recorder.mimeType || 'audio/webm').split(';')[0] });
      if (blob.size > 0) doneRef.current(blob);
    };
    stopRef.current = stop;
    recorder.start(250);
    setState('listening');
    frame = requestAnimationFrame(tick);
  }, [maxMs, silenceMs]);

  const stop = useCallback(() => stopRef.current(), []);
  return { state, level, start, stop };
}
