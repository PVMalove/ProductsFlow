import { useInfiniteQuery } from '@tanstack/react-query';
import { getProducts } from '@/lib/api/products';

export const getCatalogQueryOptions = (category?: string | null) => ({
  queryKey: ['products', { category }],
  queryFn: ({ pageParam }: { pageParam: string | null }) => getProducts(pageParam, category),
  initialPageParam: null as string | null,
  getNextPageParam: (lastPage: { meta: { next_cursor: string | null } }) => lastPage.meta.next_cursor || null,
});

export function useCursorInfiniteQuery(category?: string | null) {
  return useInfiniteQuery(getCatalogQueryOptions(category));
}
