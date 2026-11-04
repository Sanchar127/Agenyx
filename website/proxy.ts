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

function isAuthRequiredPath(pathname: string): boolean {
  return AUTH_REQUIRED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + '/'),
  );
}

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

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
