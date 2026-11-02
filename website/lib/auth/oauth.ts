const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000';

export const OAUTH_PROVIDERS = ['github', 'google'] as const;

export type OAuthProvider = (typeof OAUTH_PROVIDERS)[number];

export const OAUTH_AUTHORIZE_URLS: Record<
  OAuthProvider,
  string
> = {
  github: 'https://github.com/login/oauth/authorize',
  google: 'https://accounts.google.com/o/oauth2/v2/auth',
};

export const OAUTH_SCOPES: Record<OAuthProvider, string> = {
  github: 'read:user',
  google: 'openid email profile',
};

export function getOAuthClientId(provider: OAuthProvider): string | undefined {
  if (provider === 'github') {
    return process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID;
  }

  return process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
}

export function getOAuthCallbackUrl(
  provider: OAuthProvider,
): string {
  return `${SITE_URL}/auth/${provider}/callback`;
}

export function createOAuthState(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }

  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getOAuthAuthorizeUrl(
  provider: OAuthProvider,
  state: string,
): string {
  const clientId = getOAuthClientId(provider);

  if (!clientId) {
    throw new Error(
      `OAuth client id is not configured for provider "${provider}"`,
    );
  }

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: getOAuthCallbackUrl(provider),
    state,
  });

  if (provider === 'google') {
    params.set('response_type', 'code');
    params.set('scope', OAUTH_SCOPES.google);
  } else {
    params.set('scope', OAUTH_SCOPES.github);
  }

  return `${OAUTH_AUTHORIZE_URLS[provider]}?${params.toString()}`;
}
