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

const PROTECTED_ROUTES = ['/playground'];
const AUTH_ONLY_ROUTES = ['/login', '/signup'];

function isProtected(pathname: string): boolean {
  return PROTECTED_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
}

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Authentication
  const session = getSessionCookie(request);

  // Protect routes requiring authentication.
  if (isProtected(pathname) && !session) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('callbackUrl', pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Redirect authenticated users away from login/signup.
  if (session && AUTH_ONLY_ROUTES.includes(pathname)) {
    return NextResponse.redirect(new URL('/playground', request.url));
  }

  // Fumadocs: rewrite .md URLs.
  const suffixResult = rewriteSuffix(pathname);

  if (suffixResult) {
    return NextResponse.rewrite(new URL(suffixResult, request.nextUrl));
  }

  // Fumadocs: rewrite markdown-preferred requests.
  if (isMarkdownPreferred(request)) {
    const docsResult = rewriteDocs(pathname);

    if (docsResult) {
      return NextResponse.rewrite(new URL(docsResult, request.nextUrl), {
        headers: { Vary: 'Accept' },
      });
    }
  }

  return NextResponse.next();
}
