import { jwtDecode } from 'jwt-decode';
import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

const AUTHENTICATED_ROUTES = ['/admin', '/owner', '/support'];

function redirectToLogin(request: NextRequest): NextResponse {
  const loginUrl = new URL('/login', request.url);
  loginUrl.searchParams.set('callbackUrl', request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}

export function proxy(request: NextRequest) {
  const requiresAuthentication = AUTHENTICATED_ROUTES.some((route) =>
    request.nextUrl.pathname.startsWith(route),
  );
  if (!requiresAuthentication) return NextResponse.next();

  const accessToken = request.cookies.get('accessToken')?.value;
  if (!accessToken) return redirectToLogin(request);

  try {
    const decoded = jwtDecode<{ exp?: number }>(accessToken);
    if (decoded.exp !== undefined && decoded.exp * 1000 <= Date.now()) {
      return redirectToLogin(request);
    }
  } catch {
    return redirectToLogin(request);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|login).*)'],
};
