'use client';

import { ProductView } from '@/lib/api/products';
import { useCursorInfiniteQuery } from '@/hooks/useCursorInfiniteQuery';
import { useInView } from 'react-intersection-observer';
import { useEffect, useState, FormEvent } from 'react';
import { useAuthStore } from '@/lib/store';
import { Button } from '@/components/ui/button';
import { useRouter, useSearchParams } from 'next/navigation';
import { Input } from '@/components/ui/input';

interface CatalogListProps {
  category?: string | null;
  min_price?: number | null;
  max_price?: number | null;
  sort?: string | null;
}

export default function CatalogList({ category, min_price, max_price, sort }: CatalogListProps = {}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  
  const [minPriceInput, setMinPriceInput] = useState(min_price?.toString() || '');
  const [maxPriceInput, setMaxPriceInput] = useState(max_price?.toString() || '');
  const [sortInput, setSortInput] = useState(sort || 'newest');

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    status,
  } = useCursorInfiniteQuery(category, min_price, max_price, sort);

  const { ref, inView } = useInView();
  const { actor } = useAuthStore();

  const applyFilters = (e: FormEvent) => {
    e.preventDefault();
    const params = new URLSearchParams(searchParams.toString());
    if (minPriceInput) params.set('min_price', minPriceInput);
    else params.delete('min_price');
    
    if (maxPriceInput) params.set('max_price', maxPriceInput);
    else params.delete('max_price');
    
    if (sortInput && sortInput !== 'newest') params.set('sort', sortInput);
    else params.delete('sort');
    
    router.push(`?${params.toString()}`);
  };

  useEffect(() => {
    if (inView && hasNextPage) {
      fetchNextPage();
    }
  }, [inView, hasNextPage, fetchNextPage]);

  if (status === 'pending') {
    return (
      <div aria-label="Loading..." className="flex flex-col gap-8 w-full max-w-4xl mx-auto p-4">
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
      <form onSubmit={applyFilters} className="flex flex-wrap gap-4 items-end mb-4 bg-white dark:bg-zinc-900 p-4 rounded-lg shadow-sm">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="min_price" className="text-sm font-medium">Min Price</label>
          <Input 
            id="min_price" 
            type="number" 
            min="0"
            step="0.01"
            placeholder="0.00" 
            value={minPriceInput} 
            onChange={(e) => setMinPriceInput(e.target.value)} 
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="max_price" className="text-sm font-medium">Max Price</label>
          <Input 
            id="max_price" 
            type="number" 
            min="0"
            step="0.01"
            placeholder="999.99" 
            value={maxPriceInput} 
            onChange={(e) => setMaxPriceInput(e.target.value)} 
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="sort" className="text-sm font-medium">Sort By</label>
          <select 
            id="sort"
            className="flex h-10 w-full items-center justify-between rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm ring-offset-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-950 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-950 dark:ring-offset-zinc-950 dark:placeholder:text-zinc-400 dark:focus:ring-zinc-300"
            value={sortInput}
            onChange={(e) => setSortInput(e.target.value)}
          >
            <option value="newest">Newest</option>
            <option value="price_asc">Price: Low to High</option>
            <option value="price_desc">Price: High to Low</option>
          </select>
        </div>
        <Button type="submit">Apply</Button>
      </form>

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
