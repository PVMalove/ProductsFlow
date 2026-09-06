import { buildApiBaseUrl } from '@/lib/api-url';

describe('buildApiBaseUrl', () => {
  it('uses the same-origin API prefix by default', () => {
    expect(buildApiBaseUrl()).toBe('/api/v1');
  });

  it('adds the API prefix to a configured Gateway origin', () => {
    expect(buildApiBaseUrl('http://gateway.test/')).toBe(
      'http://gateway.test/api/v1',
    );
  });

  it('does not duplicate an explicitly configured API prefix', () => {
    expect(buildApiBaseUrl('http://gateway.test/api/v1')).toBe(
      'http://gateway.test/api/v1',
    );
  });
});
