import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { jwtDecode } from 'jwt-decode';

// Define route prefixes and the roles allowed to access them.
// Example: '/admin': ['admin']
const ROLE_PROTECTED_ROUTES: Record<string, string[]> = {
  '/admin': ['admin'],
  // Add other protected routes here
};

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const requiredRoles = Object.entries(ROLE_PROTECTED_ROUTES).find(([route]) =>
    pathname.startsWith(route)
  )?.[1];

  if (requiredRoles) {
    const accessToken = request.cookies.get('accessToken')?.value;

    if (!accessToken) {
      const loginUrl = new URL('/login', request.url);
      loginUrl.searchParams.set('callbackUrl', pathname);
      return NextResponse.redirect(loginUrl);
    }

    try {
      const decoded = jwtDecode<{ role?: string }>(accessToken);
      const userRole = decoded.role || 'user'; // default to user if not specified

      if (!requiredRoles.includes(userRole)) {
        return new NextResponse(
          `You don't have permission to access this page. Required roles: ${requiredRoles.join(', ')}`,
          { status: 403 }
        );
      }
    } catch {
      // Token is invalid or expired
      const loginUrl = new URL('/login', request.url);
      loginUrl.searchParams.set('callbackUrl', pathname);
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|login).*)'],
};
