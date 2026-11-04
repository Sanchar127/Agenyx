import { NextRequest, NextResponse } from 'next/server';
import { isMarkdownPreferred, rewritePath } from 'fumadocs-core/negotiation';
import { docsContentRoute, docsRoute } from '@/lib/shared';
import { getSessionCookie } from '@/lib/auth/session';

const { rewrite: rewriteDocs } = rewritePath(
  `${docsRoute}{/*path}`,
  `${docsContentRoute}{/*path}/content.md`,
);
const { rewrite: rewriteSuffix } = rewritePath(
  `${docsRoute}{/*path}.md`,
  `${docsContentRoute}{/*path}/content.md`,
);

// Paths that require authentication.
const AUTH_REQUIRED_PATHS = ['/playground'];

// Paths that are rate-limited (login/oauth).
const RATE_LIMITED_PATHS = ['/auth/', '/login', '/signup'];

// In-memory token bucket for rate limiting auth endpoints.
// Key: IP address, Value: { tokens, lastUpdate }
const rateLimitBuckets = new Map<string, { tokens: number; lastUpdate: number }>();

const RATE_LIMIT_RATE = 5; // tokens per second
const RATE_LIMIT_BURST = 10; // max burst

function getClientIP(request: NextRequest): string {
  const forwarded = request.headers.get('x-forwarded-for');
  if (forwarded) {
    return forwarded.split(',')[0].trim();
  }
  const realIP = request.headers.get('x-real-ip');
  if (realIP) {
    return realIP;
  }
  return 'unknown';
}

function tokenBucketAllow(ip: string): boolean {
  const now = Date.now();
  let bucket = rateLimitBuckets.get(ip);

  if (!bucket) {
    bucket = { tokens: RATE_LIMIT_BURST, lastUpdate: now };
    rateLimitBuckets.set(ip, bucket);
    return true;
  }

  // Refill tokens based on elapsed time.
  const elapsed = (now - bucket.lastUpdate) / 1000; // seconds
  bucket.tokens += elapsed * RATE_LIMIT_RATE;
  if (bucket.tokens > RATE_LIMIT_BURST) {
    bucket.tokens = RATE_LIMIT_BURST;
  }
  bucket.lastUpdate = now;

  // Clean up old buckets occasionally.
  if (rateLimitBuckets.size > 10000) {
    const cutoff = now - 10 * 60 * 1000; // 10 minutes
    for (const [key, b] of rateLimitBuckets.entries()) {
      if (b.lastUpdate < cutoff) {
        rateLimitBuckets.delete(key);
      }
    }
  }

  if (bucket.tokens < 1) {
    return false;
  }

  bucket.tokens -= 1;
  return true;
}

function isRateLimitedPath(pathname: string): boolean {
  return RATE_LIMITED_PATHS.some((p) => pathname.startsWith(p));
}

function isAuthRequiredPath(pathname: string): boolean {
  return AUTH_REQUIRED_PATHS.some((p) => pathname === p || pathname.startsWith(p + '/'));
}

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // --- Rate limiting for auth/login endpoints ---
  if (isRateLimitedPath(pathname) && request.method === 'POST') {
    const ip = getClientIP(request);
    if (!tokenBucketAllow(ip)) {
      return new NextResponse(
        JSON.stringify({ error: 'rate limit exceeded' }),
        {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': '1',
          },
        },
      );
    }
  }

  // --- Protect /playground: require session ---
  if (isAuthRequiredPath(pathname)) {
    const session = getSessionCookie(request);
    if (!session) {
      const loginUrl = new URL('/login', request.url);
      loginUrl.searchParams.set('reason', 'auth_required');
      return NextResponse.redirect(loginUrl);
    }
  }

  // --- Fumadocs proxy: rewrite docs URLs ---
  const result = rewriteSuffix(request.nextUrl.pathname);
  if (result) {
    return NextResponse.rewrite(new URL(result, request.nextUrl));
  }

  if (isMarkdownPreferred(request)) {
    const result = rewriteDocs(request.nextUrl.pathname);

    if (result) {
      return NextResponse.rewrite(new URL(result, request.nextUrl), {
        headers: { Vary: 'Accept' },
      });
    }
  }

  return NextResponse.next();
}
