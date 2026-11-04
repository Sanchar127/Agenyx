import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';

import { getOAuthAuthorizeUrl } from '@/lib/auth/oauth';

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
  const cookieStore = await cookies();

  cookieStore.set('agenyx_oauth_state', state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 300,
  });

  const redirectUri = `${process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'}/auth/github/callback`;

  return NextResponse.redirect(
    `${GITHUB_AUTHORIZE_URL}?client_id=${clientId}&redirect_uri=${redirectUri}&state=${state}&scope=read:user`,
  );
}
