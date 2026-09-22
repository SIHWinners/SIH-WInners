import bundleAnalyzer from '@next/bundle-analyzer';
import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');
const withAnalyzer = bundleAnalyzer({ enabled: process.env.ANALYZE === '1' });

const gateway = process.env.GATEWAY_URL ?? 'http://127.0.0.1:8080';
const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8080/ws';

// Content Security Policy: no third-party scripts at all. Map tiles are the only external
// images; everything else (fonts included) is self-hosted by next/font.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'" + (process.env.NODE_ENV === 'development' ? " 'unsafe-eval'" : ''),
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://*.tile.openstreetmap.org",
  "font-src 'self' data:",
  `connect-src 'self' ${wsUrl} ${gateway}`,
  "media-src 'self' blob: data:",
  "worker-src 'self' blob:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join('; ');

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  compress: true,
  transpilePackages: ['@sm/i18n', '@sm/ui', '@sm/contracts'],
  experimental: {
    optimizePackageImports: ['@tanstack/react-query'],
  },
  images: { formats: ['image/avif', 'image/webp'] },
  env: { NEXT_PUBLIC_WS_URL: wsUrl },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Content-Security-Policy', value: csp },
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
          { key: 'Permissions-Policy', value: 'camera=(self), microphone=(self), geolocation=(self)' },
        ],
      },
    ];
  },
};

export default withAnalyzer(withNextIntl(config));
