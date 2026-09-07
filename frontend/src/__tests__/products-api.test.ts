import { QueryClient } from '@tanstack/react-query';
import { getCatalogQueryOptions } from '@/hooks/useCursorInfiniteQuery';
import { getProducts } from '@/lib/api/products';
import { DEFAULT_CATALOG_FILTERS } from '@/lib/catalog-filters';
import { shouldRetryQuery } from '@/lib/query-retry';

describe('getProducts pagination', () => {
  const originalApiUrl = process.env.NEXT_PUBLIC_API_URL;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = 'http://gateway.test';
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({
        data: [],
        meta: {
          next_cursor: null,
          prev_cursor: null,
          has_more: false,
          has_prev: true,
        },
      }),
    });
  });

  afterAll(() => {
    if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = originalApiUrl;
  });

  it('sends cursor and sort when requesting the next catalog page', async () => {
    await getProducts({
      cursor: 'opaque-cursor',
      query: null,
      category: 'Tools',
      minPrice: 10,
      maxPrice: 100,
      sort: 'newest',
    });

    expect(global.fetch).toHaveBeenCalledWith(
      'http://gateway.test/api/v1/products/search?category=Tools&min_price=10&max_price=100&after=opaque-cursor&sort=newest',
      { cache: 'no-store' },
    );
  });

  it('does not retry a catalog request rejected with a client error', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Content',
    });
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: shouldRetryQuery,
          retryDelay: 0,
        },
      },
    });

    await expect(
      queryClient.fetchInfiniteQuery(
        getCatalogQueryOptions(DEFAULT_CATALOG_FILTERS),
      ),
    ).rejects.toThrow('Failed to fetch products');

    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
