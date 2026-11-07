import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const SESSION_COOKIE = 'agenyx_session';

// Routes that require an active session.
const PROTECTED_ROUTES = ['/playground'];

// Routes that authenticated users should be redirected away from.
const AUTH_ONLY_ROUTES = ['/login', '/signup'];

function isProtected(pathname: string): boolean {
  return PROTECTED_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const session = request.cookies.get(SESSION_COOKIE)?.value;

  // Protect dashboard/playground routes: require a session.
  if (isProtected(pathname) && !session) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('callbackUrl', pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Already authenticated: send login/signup visitors to the playground.
  if (session && AUTH_ONLY_ROUTES.includes(pathname)) {
    return NextResponse.redirect(new URL('/playground', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/playground/:path*', '/login', '/signup'],
};
