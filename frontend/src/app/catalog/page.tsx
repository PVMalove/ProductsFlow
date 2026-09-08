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
    <main className="min-h-screen px-5 py-8 sm:px-8">
      <div className="mx-auto mb-7 flex w-full max-w-6xl items-end justify-between gap-4">
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-blue-300">ProductsFlow</p>
          <h1 className="text-3xl font-bold tracking-tight text-slate-100">
            Каталог товаров {filters.category ? `— ${filters.category}` : ''}
          </h1>
        </div>
      </div>
      
      <HydrationBoundary state={dehydrate(queryClient)}>
        <CatalogList filters={filters} />
      </HydrationBoundary>
    </main>
  );
}
