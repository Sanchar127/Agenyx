import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';

import { AGENYX_API_BASE_URL } from '@/lib/api/client';
import { setSessionCookie } from '@/lib/auth/session';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get('code');
  const state = searchParams.get('state');
  const cookieStore = await cookies();
  const storedState = cookieStore.get('agenyx_oauth_state')?.value;

  if (!code || !state || state !== storedState) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('error', 'oauth_state_mismatch');

    return NextResponse.redirect(loginUrl);
  }

  cookieStore.delete('agenyx_oauth_state');

  const tokenEndpoint = `${AGENYX_API_BASE_URL}/auth/google/token`;

  let exchangeFailed = true;
  let responseBody: unknown = null;

  try {
    const exchangeResponse = await fetch(tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code,
        client_id: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID,
        redirect_uri: `${process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'}/auth/google/callback`,
      }),
    });

    exchangeFailed = !exchangeResponse.ok;

    try {
      responseBody = await exchangeResponse.json();
    } catch {
      responseBody = null;
    }
  } catch {
    exchangeFailed = true;
  }

  const redirectUrl = new URL('/', request.url);

  if (exchangeFailed) {
    redirectUrl.pathname = '/login';
    redirectUrl.searchParams.set('error', 'oauth_exchange_failed');

    return NextResponse.redirect(redirectUrl);
  }

  // On successful token exchange, create a response that sets the session
  // cookie and redirects to the playground.
  const secure = process.env.NODE_ENV === 'production';
  const sessionToken = crypto.randomUUID();

  const nextResponse = NextResponse.redirect(new URL('/playground', request.url));
  setSessionCookie(nextResponse, sessionToken, secure);

  // Also set the cookie via the cookieStore for Next.js to pick up.
  cookieStore.set('agenyx_session', sessionToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24, // 24 hours
  });

  return nextResponse;
}
