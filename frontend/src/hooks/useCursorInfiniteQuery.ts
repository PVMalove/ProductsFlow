import { infiniteQueryOptions, useInfiniteQuery } from '@tanstack/react-query';
import { getProducts } from '@/lib/api/products';
import type { CatalogFilters } from '@/lib/catalog-filters';

export const getCatalogQueryOptions = (filters: CatalogFilters) =>
  infiniteQueryOptions({
    queryKey: ['products', filters] as const,
    queryFn: ({ pageParam }) => getProducts({ ...filters, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.meta.next_cursor ?? undefined,
  });

export function useCursorInfiniteQuery(filters: CatalogFilters) {
  return useInfiniteQuery(getCatalogQueryOptions(filters));
}
