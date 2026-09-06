import { useInfiniteQuery, QueryKey } from '@tanstack/react-query';
import { OffsetApiResponse } from '@/lib/api/users';

export function getOffsetQueryOptions<T>(
  queryKey: QueryKey,
  fetchFn: (pageIndex: number) => Promise<OffsetApiResponse<T[]>>
) {
  return {
    queryKey,
    queryFn: ({ pageParam = 1 }: { pageParam: number }) => fetchFn(pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage: OffsetApiResponse<T[]>) => {
      const { page_index, total_pages } = lastPage.meta;
      if (page_index < total_pages) {
        return page_index + 1;
      }
      return null;
    },
  };
}

export function useOffsetInfiniteQuery<T>(
  queryKey: QueryKey,
  fetchFn: (pageIndex: number) => Promise<OffsetApiResponse<T[]>>
) {
  return useInfiniteQuery(getOffsetQueryOptions<T>(queryKey, fetchFn));
}
