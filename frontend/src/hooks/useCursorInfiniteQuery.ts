import { useInfiniteQuery } from '@tanstack/react-query';
import { getProducts } from '@/lib/api/products';

export const getCatalogQueryOptions = (category?: string | null, min_price?: number | null, max_price?: number | null) => ({
  queryKey: ['products', { category, min_price, max_price }],
  queryFn: ({ pageParam }: { pageParam: string | null }) => getProducts(pageParam, category, min_price, max_price),
  initialPageParam: null as string | null,
  getNextPageParam: (lastPage: { meta: { next_cursor: string | null } }) => lastPage.meta.next_cursor || null,
});

export function useCursorInfiniteQuery(category?: string | null, min_price?: number | null, max_price?: number | null) {
  return useInfiniteQuery(getCatalogQueryOptions(category, min_price, max_price));
}
