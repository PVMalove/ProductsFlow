import { dehydrate, HydrationBoundary, QueryClient } from '@tanstack/react-query';
import CatalogList from '@/components/catalog/catalog-list';
import { getCatalogQueryOptions } from '@/hooks/useCursorInfiniteQuery';

export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const queryClient = new QueryClient();
  const params = await searchParams;
  const category = typeof params.category === 'string' ? params.category : null;
  const min_price = typeof params.min_price === 'string' && !isNaN(Number(params.min_price)) ? Number(params.min_price) : null;
  const max_price = typeof params.max_price === 'string' && !isNaN(Number(params.max_price)) ? Number(params.max_price) : null;
  const sort = typeof params.sort === 'string' ? params.sort : null;

  await queryClient.prefetchInfiniteQuery(getCatalogQueryOptions(category, min_price, max_price, sort));

  return (
    <main className="flex min-h-screen flex-col items-center p-8 bg-zinc-50 dark:bg-black text-black dark:text-zinc-50">
      <div className="w-full max-w-4xl flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Products Catalog {category ? `- ${category}` : ''}</h1>
      </div>
      
      <HydrationBoundary state={dehydrate(queryClient)}>
        <CatalogList category={category} min_price={min_price} max_price={max_price} sort={sort} />
      </HydrationBoundary>
    </main>
  );
}
