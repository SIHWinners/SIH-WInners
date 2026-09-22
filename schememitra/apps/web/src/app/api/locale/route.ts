import { isLocale } from '@sm/i18n';
import { NextResponse, type NextRequest } from 'next/server';

export async function POST(req: NextRequest) {
  const { locale } = (await req.json().catch(() => ({}))) as { locale?: string };
  if (!isLocale(locale)) return NextResponse.json({ status: 422 }, { status: 422 });
  const res = NextResponse.json({ locale });
  res.cookies.set('sm_locale', locale, { path: '/', sameSite: 'lax', maxAge: 60 * 60 * 24 * 365 });
  return res;
}
