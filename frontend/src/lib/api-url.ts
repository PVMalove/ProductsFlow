const API_PREFIX = '/api/v1';

export function buildApiBaseUrl(origin?: string): string {
  const normalizedOrigin = origin?.replace(/\/+$/, '');
  if (!normalizedOrigin) return API_PREFIX;
  if (normalizedOrigin.endsWith(API_PREFIX)) return normalizedOrigin;
  return `${normalizedOrigin}${API_PREFIX}`;
}
