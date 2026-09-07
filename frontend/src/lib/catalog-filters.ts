export const CATALOG_SORT_OPTIONS = [
  'newest',
  'price_asc',
  'price_desc',
] as const;

export type CatalogSort = (typeof CATALOG_SORT_OPTIONS)[number];

export interface CatalogFilters {
  query: string | null;
  category: string | null;
  minPrice: number | null;
  maxPrice: number | null;
  sort: CatalogSort;
}

export const DEFAULT_CATALOG_FILTERS: CatalogFilters = {
  query: null,
  category: null,
  minPrice: null,
  maxPrice: null,
  sort: 'newest',
};

type CatalogSearchParams = Record<string, string | string[] | undefined>;

function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function parsePrice(value: string | undefined): number | null {
  if (!value?.trim()) return null;
  const price = Number(value);
  return Number.isFinite(price) && price >= 0 ? price : null;
}

export function isCatalogSort(value: string | undefined): value is CatalogSort {
  return CATALOG_SORT_OPTIONS.some((option) => option === value);
}

export function parseCatalogFilters(params: CatalogSearchParams): CatalogFilters {
  const qRaw = firstValue(params.q)?.trim();
  const query = qRaw && qRaw.length >= 2 ? qRaw : null;
  const category = firstValue(params.category)?.trim() || null;
  const sort = firstValue(params.sort);

  return {
    query,
    category,
    minPrice: parsePrice(firstValue(params.min_price)),
    maxPrice: parsePrice(firstValue(params.max_price)),
    sort: isCatalogSort(sort) ? sort : DEFAULT_CATALOG_FILTERS.sort,
  };
}

export function serializeCatalogFilters(filters: CatalogFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.query) params.set('q', filters.query);
  if (filters.category) params.set('category', filters.category);
  if (filters.minPrice !== null) params.set('min_price', filters.minPrice.toString());
  if (filters.maxPrice !== null) params.set('max_price', filters.maxPrice.toString());
  
  if (filters.sort !== DEFAULT_CATALOG_FILTERS.sort) {
    params.set('sort', filters.sort);
  }
  
  return params;
}

export function getCatalogFiltersKey(filters: CatalogFilters): string {
  return [
    filters.query,
    filters.category,
    filters.minPrice,
    filters.maxPrice,
    filters.sort,
  ].join(':');
}
