import { dehydrate, HydrationBoundary, QueryClient } from '@tanstack/react-query';
import CatalogList from '@/components/catalog/catalog-list';
import { getCatalogQueryOptions } from '@/hooks/useCursorInfiniteQuery';
import { parseCatalogFilters } from '@/lib/catalog-filters';

export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const queryClient = new QueryClient();
  const filters = parseCatalogFilters(await searchParams);

  await queryClient.prefetchInfiniteQuery(getCatalogQueryOptions(filters));

  return (
    <main className="flex min-h-screen flex-col items-center p-8 bg-zinc-50 dark:bg-black text-black dark:text-zinc-50">
      <div className="w-full max-w-4xl flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          Products Catalog {filters.category ? `- ${filters.category}` : ''}
        </h1>
      </div>
      
      <HydrationBoundary state={dehydrate(queryClient)}>
        <CatalogList filters={filters} />
      </HydrationBoundary>
    </main>
  );
}
