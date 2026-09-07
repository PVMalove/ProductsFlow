'use client';

import { FormEvent, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { CatalogFilters, CatalogSort } from '@/lib/catalog-filters';

interface CatalogFiltersFormProps {
  filters: CatalogFilters;
}

function setOptionalParam(
  params: URLSearchParams,
  name: string,
  value: string,
) {
  if (value) params.set(name, value);
  else params.delete(name);
}

export function CatalogFiltersForm({ filters }: CatalogFiltersFormProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [q, setQ] = useState(filters.q ?? '');
  const [minPrice, setMinPrice] = useState(filters.minPrice?.toString() ?? '');
  const [maxPrice, setMaxPrice] = useState(filters.maxPrice?.toString() ?? '');
  const [sort, setSort] = useState<CatalogSort>(filters.sort);

  const isSearchInvalid = q.trim().length === 1;

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSearchInvalid) return;
    
    const params = new URLSearchParams();
    if (filters.category) params.set('category', filters.category);
    setOptionalParam(params, 'q', q.trim());
    setOptionalParam(params, 'min_price', minPrice);
    setOptionalParam(params, 'max_price', maxPrice);

    if (sort === 'newest') params.delete('sort');
    else params.set('sort', sort);

    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <form
      onSubmit={applyFilters}
      className="mb-4 flex flex-wrap items-end gap-4 rounded-lg bg-white p-4 shadow-sm dark:bg-zinc-900"
    >
      <div className="flex flex-col gap-1.5 w-full sm:w-auto sm:flex-grow">
        <Label htmlFor="q">Search</Label>
        <Input
          id="q"
          type="text"
          placeholder="Search products..."
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
        {isSearchInvalid && (
          <span className="text-xs text-red-500">Минимум 2 символа</span>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="min_price">Min Price</Label>
        <Input
          id="min_price"
          type="number"
          min="0"
          step="0.01"
          placeholder="0.00"
          value={minPrice}
          onChange={(event) => setMinPrice(event.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="max_price">Max Price</Label>
        <Input
          id="max_price"
          type="number"
          min="0"
          step="0.01"
          placeholder="999.99"
          value={maxPrice}
          onChange={(event) => setMaxPrice(event.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="sort">Sort By</Label>
        <select
          id="sort"
          className="flex h-10 w-full items-center justify-between rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm ring-offset-white focus:outline-none focus:ring-2 focus:ring-zinc-950 focus:ring-offset-2 dark:border-zinc-800 dark:bg-zinc-950 dark:ring-offset-zinc-950 dark:focus:ring-zinc-300"
          value={sort}
          onChange={(event) => setSort(event.target.value as CatalogSort)}
        >
          <option value="newest">Newest</option>
          <option value="price_asc">Price: Low to High</option>
          <option value="price_desc">Price: High to Low</option>
        </select>
      </div>
      <Button type="submit" disabled={isSearchInvalid}>Apply</Button>
    </form>
  );
}
