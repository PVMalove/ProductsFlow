import Cookies from 'js-cookie';

export const ACCESS_TOKEN_COOKIE = 'accessToken';

export function getAccessToken(): string | undefined {
  return Cookies.get(ACCESS_TOKEN_COOKIE);
}

export function setAccessToken(token: string): void {
  Cookies.set(ACCESS_TOKEN_COOKIE, token, {
    path: '/',
    sameSite: 'strict',
    secure: typeof window !== 'undefined' && window.location.protocol === 'https:',
  });
}

export function clearAccessToken(): void {
  Cookies.remove(ACCESS_TOKEN_COOKIE, { path: '/' });
}
