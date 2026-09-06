import { dehydrate, HydrationBoundary, QueryClient } from '@tanstack/react-query';
import { getProducts } from '@/lib/api/products';
import CatalogList from '@/components/catalog/catalog-list';

export default async function Home() {
  const queryClient = new QueryClient();

  await queryClient.prefetchInfiniteQuery({
    queryKey: ['products'],
    queryFn: () => getProducts(null),
    initialPageParam: null as string | null,
  });

  return (
    <main className="flex min-h-screen flex-col items-center p-8 bg-zinc-50 dark:bg-black text-black dark:text-zinc-50">
      <div className="w-full max-w-4xl flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Products Catalog</h1>
      </div>
      
      <HydrationBoundary state={dehydrate(queryClient)}>
        <CatalogList />
      </HydrationBoundary>
    </main>
  );
}
