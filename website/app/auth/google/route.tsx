import { NextResponse } from 'next/server';

const GOOGLE_AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/v2/auth';

export async function GET() {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

  if (!clientId) {
    return NextResponse.json(
      { error: 'Google OAuth is not configured' },
      { status: 503 },
    );
  }

  const state = crypto.randomUUID();
  const redirectUri = `${process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'}/auth/google/callback`;

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: 'openid email profile',
    state,
  });

  const response = NextResponse.redirect(
    `${GOOGLE_AUTHORIZE_URL}?${params.toString()}`,
  );

  // Carry the CSRF state cookie on the redirect so the callback can verify it.
  response.cookies.set('agenyx_oauth_state', state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 300,
  });

  return response;
}
