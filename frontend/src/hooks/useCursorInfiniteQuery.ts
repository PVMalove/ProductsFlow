import { useInfiniteQuery } from '@tanstack/react-query';
import { getProducts } from '@/lib/api/products';

export const getCatalogQueryOptions = () => ({
  queryKey: ['products'],
  queryFn: ({ pageParam }: { pageParam: string | null }) => getProducts(pageParam),
  initialPageParam: null as string | null,
  getNextPageParam: (lastPage: { meta: { next_cursor: string | null } }) => lastPage.meta.next_cursor || null,
});

export function useCursorInfiniteQuery() {
  return useInfiniteQuery(getCatalogQueryOptions());
}
