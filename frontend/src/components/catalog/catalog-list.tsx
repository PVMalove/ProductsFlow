'use client';

import { useEffect } from 'react';
import { useInView } from 'react-intersection-observer';

import { CatalogFiltersForm } from '@/components/catalog/catalog-filters-form';
import { ProductCard } from '@/components/catalog/product-card';
import { useCursorInfiniteQuery } from '@/hooks/useCursorInfiniteQuery';
import {
  DEFAULT_CATALOG_FILTERS,
} from '@/lib/catalog-filters';
import type { CatalogFilters } from '@/lib/catalog-filters';
import { useAuthStore } from '@/lib/store';

interface CatalogListProps {
  filters?: CatalogFilters;
}

function CatalogSkeleton() {
  return (
    <div
      aria-label="Loading..."
      className="mx-auto flex w-full max-w-4xl flex-col gap-8 p-4"
    >
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <div
            key={index}
            className="flex animate-pulse flex-col gap-2 rounded-lg border bg-white p-4 shadow-sm dark:bg-zinc-900"
          >
            <div className="mb-2 h-6 w-3/4 rounded bg-gray-200 dark:bg-zinc-800" />
            <div className="h-4 w-full flex-grow rounded bg-gray-200 dark:bg-zinc-800" />
            <div className="h-4 w-5/6 rounded bg-gray-200 dark:bg-zinc-800" />
            <div className="mt-4 flex items-center justify-between">
              <div className="h-5 w-16 rounded bg-gray-200 dark:bg-zinc-800" />
              <div className="h-5 w-20 rounded bg-gray-200 dark:bg-zinc-800" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CatalogList({
  filters = DEFAULT_CATALOG_FILTERS,
}: CatalogListProps) {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    status,
  } = useCursorInfiniteQuery(filters);
  const { ref, inView } = useInView();
  const actor = useAuthStore((state) => state.actor);

  useEffect(() => {
    if (inView && hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [fetchNextPage, hasNextPage, inView, isFetchingNextPage]);

  if (status === 'pending') return <CatalogSkeleton />;

  if (status === 'error') {
    return (
      <div role="alert" className="p-8 text-center text-red-500">
        Error loading products
      </div>
    );
  }

  const products = data.pages.flatMap((page) => page.data);
  const filtersKey = [
    filters.category,
    filters.minPrice,
    filters.maxPrice,
    filters.sort,
  ].join(':');

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 p-4">
      <CatalogFiltersForm key={filtersKey} filters={filters} />

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {products.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            canEdit={actor?.id === product.user_id || actor?.role === 'admin'}
          />
        ))}
      </div>

      <div ref={ref} className="flex w-full justify-center p-4">
        <span className="text-gray-500">
          {isFetchingNextPage
            ? 'Loading more...'
            : hasNextPage
              ? 'Scroll for more'
              : 'No more products'}
        </span>
      </div>
    </div>
  );
}
