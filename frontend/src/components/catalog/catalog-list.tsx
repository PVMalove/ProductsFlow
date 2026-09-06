'use client';

import { ProductView } from '@/lib/api/products';
import { useCursorInfiniteQuery } from '@/hooks/useCursorInfiniteQuery';
import { useInView } from 'react-intersection-observer';
import { useEffect } from 'react';
import { useAuthStore } from '@/lib/store';
import { Button } from '@/components/ui/button';

interface CatalogListProps {
  category?: string | null;
}

export default function CatalogList({ category }: CatalogListProps = {}) {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    status,
  } = useCursorInfiniteQuery(category);

  const { ref, inView } = useInView();
  const { actor } = useAuthStore();

  useEffect(() => {
    if (inView && hasNextPage) {
      fetchNextPage();
    }
  }, [inView, hasNextPage, fetchNextPage]);

  if (status === 'pending') {
    return (
      <div className="flex flex-col gap-8 w-full max-w-4xl mx-auto p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="border rounded-lg p-4 shadow-sm flex flex-col gap-2 bg-white dark:bg-zinc-900 animate-pulse">
              <div className="h-6 bg-gray-200 dark:bg-zinc-800 rounded w-3/4 mb-2"></div>
              <div className="h-4 bg-gray-200 dark:bg-zinc-800 rounded w-full flex-grow"></div>
              <div className="h-4 bg-gray-200 dark:bg-zinc-800 rounded w-5/6"></div>
              <div className="flex justify-between items-center mt-4">
                <div className="h-5 bg-gray-200 dark:bg-zinc-800 rounded w-16"></div>
                <div className="h-5 bg-gray-200 dark:bg-zinc-800 rounded w-20"></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return <div className="p-8 text-center text-red-500">Error loading products</div>;
  }

  return (
    <div className="flex flex-col gap-8 w-full max-w-4xl mx-auto p-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {data.pages.map((page, i) => (
          <div key={i} className="contents">
            {page.data.map((product: ProductView) => {
              const canEdit = actor?.id === product.user_id || actor?.role === 'admin';

              return (
                <div key={product.id} className="border rounded-lg p-4 shadow-sm flex flex-col gap-2 bg-white dark:bg-zinc-900">
                  <h3 className="font-semibold text-lg">{product.name}</h3>
                  <p className="text-sm text-gray-500 line-clamp-2 flex-grow">{product.description}</p>
                  <div className="flex justify-between items-center mt-2">
                    <span className="font-bold">${product.price.toFixed(2)}</span>
                    <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-zinc-800 rounded-full">{product.category}</span>
                  </div>
                  {canEdit && (
                    <div className="flex gap-2 mt-2 pt-2 border-t border-gray-100 dark:border-zinc-800">
                      <Button variant="outline" size="sm" className="flex-1">Редактировать</Button>
                      <Button variant="destructive" size="sm" className="flex-1">Удалить</Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
      
      <div ref={ref} className="w-full flex justify-center p-4">
        {isFetchingNextPage ? (
          <span className="text-gray-500">Loading more...</span>
        ) : hasNextPage ? (
          <span className="text-gray-500">Scroll for more</span>
        ) : (
          <span className="text-gray-500">No more products</span>
        )}
      </div>
    </div>
  );
}
