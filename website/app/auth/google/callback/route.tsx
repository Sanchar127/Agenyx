import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { AGENYX_API_BASE_URL } from '@/lib/api/client';

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

  try {
    const exchangeResponse = await fetch(tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code,
        client_id: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID,
      }),
    });

    exchangeFailed = !exchangeResponse.ok;
  } catch {
    exchangeFailed = true;
  }

  const redirectUrl = new URL('/', request.url);

  if (exchangeFailed) {
    redirectUrl.pathname = '/login';
    redirectUrl.searchParams.set('error', 'oauth_exchange_failed');

    return NextResponse.redirect(redirectUrl);
  }

  return NextResponse.redirect(redirectUrl);
}
