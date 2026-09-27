/// <reference lib="webworker" />
import { defaultCache } from '@serwist/next/worker';
import type { PrecacheEntry, SerwistGlobalConfig } from 'serwist';
import { NetworkFirst, NetworkOnly, Serwist, StaleWhileRevalidate } from 'serwist';

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}
declare const self: ServiceWorkerGlobalScope;

/**
 * Offline behaviour (claims C13, C14). The app shell and the rule bundle are cached so a
 * citizen on a dead 2G cell can still answer questions and see an eligibility result marked
 * "provisional". Anything that changes state is never served from a cache: it goes to the
 * network, and the app queues it in IndexedDB when that fails.
 */
const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    {
      // The offline rule bundle: serve instantly, refresh in the background.
      matcher: ({ url }) => url.pathname === '/api/v1/rules/bundle',
      handler: new StaleWhileRevalidate({ cacheName: 'rules-bundle' }),
    },
    {
      // Map tiles are big and optional: keep a few, never block on them.
      matcher: ({ url }) => url.hostname.endsWith('tile.openstreetmap.org'),
      handler: new StaleWhileRevalidate({ cacheName: 'map-tiles' }),
    },
    {
      // Reads may come from cache while offline; writes must not.
      matcher: ({ url, request }) => url.pathname.startsWith('/api/') && request.method === 'GET',
      handler: new NetworkFirst({ cacheName: 'api-reads', networkTimeoutSeconds: 6 }),
    },
    { matcher: ({ url }) => url.pathname.startsWith('/api/'), handler: new NetworkOnly() },
    ...defaultCache,
  ],
  fallbacks: {
    entries: [{ url: '/offline', matcher: ({ request }) => request.destination === 'document' }],
  },
});

serwist.addEventListeners();
