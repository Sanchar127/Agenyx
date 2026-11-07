import { NextResponse } from 'next/server';

const GITHUB_AUTHORIZE_URL = 'https://github.com/login/oauth/authorize';

export async function GET() {
  const clientId = process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID;

  if (!clientId) {
    return NextResponse.json(
      { error: 'GitHub OAuth is not configured' },
      { status: 503 },
    );
  }

  const state = crypto.randomUUID();
  const redirectUri = `${process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'}/auth/github/callback`;

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    state,
    scope: 'read:user',
  });

  const response = NextResponse.redirect(
    `${GITHUB_AUTHORIZE_URL}?${params.toString()}`,
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
